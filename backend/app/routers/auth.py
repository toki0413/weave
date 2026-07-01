from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import bcrypt
import secrets
import uuid
import jwt as pyjwt
from jwt import InvalidTokenError
from datetime import datetime, timedelta, timezone
from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserLogin, Token, UserOut
from app.config import get_settings
from app.rate_limit import rate_limit
from app.services.crypto import (
    derive_key,
    generate_master_key,
    wrap_master_key,
    unwrap_master_key,
)
from app.services import key_manager
from pydantic import BaseModel, Field

router = APIRouter(prefix="/auth", tags=["auth"])

settings = get_settings()


# ========== Pydantic 请求模型（替代裸 dict）==========
class RecoveryPayload(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20, pattern=r"^1[3-9]\d{9}$")
    recovery_code: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)


class ChangePasswordPayload(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)


# ========== 工具函数 ==========
def _validate_password(password: str) -> None:
    """检查密码复杂度：至少8位，包含字母、数字和特殊字符"""
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="密码长度至少8位")
    if not re.search(r'[A-Za-z]', password):
        raise HTTPException(status_code=400, detail="密码必须包含字母")
    if not re.search(r'\d', password):
        raise HTTPException(status_code=400, detail="密码必须包含数字")
    if not re.search(r'[^A-Za-z0-9]', password):
        raise HTTPException(status_code=400, detail="密码必须包含特殊字符")


import re

def verify_password(plain: str, hashed: str) -> bool:
    if isinstance(hashed, str):
        hashed = hashed.encode('utf-8')
    return bcrypt.checkpw(plain.encode('utf-8'), hashed)


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def _derive_kek(password: str, salt: str) -> bytes:
    """用密码+salt派生KEK（Key Encryption Key）"""
    return derive_key(password, salt)


def _derive_recovery_kek(recovery_code: str, salt: str) -> bytes:
    """用恢复码+salt派生恢复密钥"""
    return derive_key(recovery_code, salt)


def _hash_recovery_code(recovery_code: str) -> str:
    return bcrypt.hashpw(recovery_code.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def _verify_recovery_code(recovery_code: str, hashed: str) -> bool:
    if isinstance(hashed, str):
        hashed = hashed.encode('utf-8')
    return bcrypt.checkpw(recovery_code.encode('utf-8'), hashed)


def _generate_recovery_code() -> str:
    """生成24字符URL安全恢复码"""
    return secrets.token_urlsafe(18)


def _cache_user_keys(user: User, password: str) -> None:
    """登录/注册时：派生KEK，解出或创建主密钥，并缓存到内存。"""
    if not user.encryption_salt:
        user.encryption_salt = secrets.token_hex(16)

    kek = _derive_kek(password, user.encryption_salt)

    if user.master_key_encrypted:
        master_key = unwrap_master_key(user.master_key_encrypted, kek)
    else:
        # 旧用户或无主密钥用户：创建新主密钥并用KEK包装
        master_key = generate_master_key()
        user.master_key_encrypted = wrap_master_key(master_key, kek)

    key_manager.set_user_keys(user.id, kek, master_key)


def _rebuild_recovery_material(user: User, master_key: bytes, recovery_code: str) -> None:
    """用新的恢复码重新加密主密钥"""
    user.recovery_salt = secrets.token_hex(16)
    rkek = _derive_recovery_kek(recovery_code, user.recovery_salt)
    user.recovery_master_key_encrypted = wrap_master_key(master_key, rkek)
    user.recovery_code_hash = _hash_recovery_code(recovery_code)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    return pyjwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    token = credentials.credentials if credentials else None
    if not token:
        raise credentials_exception
    try:
        payload = pyjwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        phone: str = payload.get("sub")
        if phone is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception
    user = db.query(User).filter(User.phone == phone).first()
    if user is None:
        raise credentials_exception
    return user


@router.post("/register", response_model=Token, dependencies=[rate_limit(3, 300)])
def register(user: UserCreate, db: Session = Depends(get_db)):
    try:
        existing = db.query(User).filter(User.phone == user.phone).first()
        if existing:
            raise HTTPException(status_code=400, detail="Phone already registered")

        _validate_password(user.password)

        user_id = str(uuid.uuid4())
        encryption_salt = secrets.token_hex(16)
        kek = _derive_kek(user.password, encryption_salt)
        master_key = generate_master_key()
        master_key_encrypted = wrap_master_key(master_key, kek)

        recovery_code = _generate_recovery_code()
        recovery_salt = secrets.token_hex(16)
        rkek = _derive_recovery_kek(recovery_code, recovery_salt)
        recovery_master_key_encrypted = wrap_master_key(master_key, rkek)

        db_user = User(
            id=user_id,
            phone=user.phone,
            hashed_password=get_password_hash(user.password),
            role=user.role,
            name=user.name or user.phone,
            encryption_salt=encryption_salt,
            master_key_encrypted=master_key_encrypted,
            recovery_code_hash=_hash_recovery_code(recovery_code),
            recovery_master_key_encrypted=recovery_master_key_encrypted,
            recovery_salt=recovery_salt,
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        key_manager.set_user_keys(db_user.id, kek, master_key)

        token = create_access_token({"sub": db_user.phone})
        return {
            "access_token": token,
            "token_type": "bearer",
            "recovery_code": recovery_code,  # 仅注册时返回一次
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger("cognitive_garden").error("Register failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="注册失败，请稍后重试")


@router.post("/login", response_model=Token, dependencies=[rate_limit(5, 300)])
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.phone == user.phone).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    _cache_user_keys(db_user, user.password)
    db.commit()

    token = create_access_token({"sub": db_user.phone})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user)):
    """登出时清除内存中的加密密钥"""
    key_manager.clear_user_key(current_user.id)
    return {"detail": "已登出"}


@router.post("/recovery", dependencies=[rate_limit(3, 300)])
def recover_account(payload: RecoveryPayload, db: Session = Depends(get_db)):
    """用恢复码重置密码并重新包装主密钥"""
    user = db.query(User).filter(User.phone == payload.phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not user.recovery_code_hash or not user.recovery_master_key_encrypted or not user.recovery_salt:
        raise HTTPException(status_code=400, detail="该账户未设置恢复码")

    if not _verify_recovery_code(payload.recovery_code, user.recovery_code_hash):
        raise HTTPException(status_code=401, detail="恢复码不正确")

    try:
        # 用恢复码解出主密钥
        rkek = _derive_recovery_kek(payload.recovery_code, user.recovery_salt)
        master_key = unwrap_master_key(user.recovery_master_key_encrypted, rkek)

        # 用新密码派生新的KEK并重新包装主密钥
        new_kek = _derive_kek(payload.new_password, user.encryption_salt)
        user.master_key_encrypted = wrap_master_key(master_key, new_kek)
        user.hashed_password = get_password_hash(payload.new_password)

        # 生成新的恢复码并重新加密主密钥
        new_recovery_code = _generate_recovery_code()
        _rebuild_recovery_material(user, master_key, new_recovery_code)

        db.commit()
        key_manager.set_user_keys(user.id, new_kek, master_key)

        return {
            "detail": "密码重置成功，请保存新的恢复码",
            "recovery_code": new_recovery_code,
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger("cognitive_garden").error("Recovery failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="恢复失败，请稍后重试")


@router.post("/change-password", dependencies=[rate_limit(5, 300)])
def change_password(payload: ChangePasswordPayload, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """修改登录密码（无需恢复码），用新密码重新包装主密钥"""
    if not verify_password(payload.old_password, current_user.hashed_password):
        raise HTTPException(status_code=401, detail="原密码不正确")

    _validate_password(payload.new_password)

    try:
        kek = key_manager.get_user_kek(current_user.id)
        master_key = key_manager.get_user_key(current_user.id)

        new_kek = _derive_kek(payload.new_password, current_user.encryption_salt)
        current_user.master_key_encrypted = wrap_master_key(master_key, new_kek)
        current_user.hashed_password = get_password_hash(payload.new_password)

        # 恢复码不变，但要用新KEK重新包装主密钥；恢复码加密的主密钥保持不变
        db.commit()
        key_manager.set_user_keys(current_user.id, new_kek, master_key)

        return {"detail": "密码修改成功"}
    except Exception as e:
        import logging
        logging.getLogger("cognitive_garden").error("Change password failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="修改密码失败")


@router.get("/recovery-code")
def get_recovery_code(current_user: User = Depends(get_current_user)):
    """返回是否已设置恢复码；不返回明文恢复码（只返回一次）"""
    return {
        "has_recovery_code": bool(current_user.recovery_code_hash),
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
    }


@router.get("/me", response_model=UserOut)
def read_me(current_user: User = Depends(get_current_user)):
    return current_user
