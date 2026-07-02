from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import bcrypt
import secrets
import uuid
import hashlib
import jwt as pyjwt
from jwt import InvalidTokenError
from datetime import datetime, timedelta, timezone
from app.database import get_db
from app.models import User, RefreshToken
from app.schemas import UserCreate, UserLogin, Token, UserOut, RefreshRequest
from app.config import get_settings
from app.rate_limit import rate_limit
from app.services import key_manager
from app.services import kms
from app.services.audit import log_audit
from app.redis_client import blacklist_token, is_token_blacklisted
from pydantic import BaseModel, Field

router = APIRouter(prefix="/auth", tags=["auth"])

settings = get_settings()


# ========== Pydantic 请求模型 ==========
class RecoveryPayload(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20, pattern=r"^1[3-9]\d{9}$")
    recovery_code: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)


class ChangePasswordPayload(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)


# ========== 工具函数 ==========
def _utc_now():
    return datetime.now(timezone.utc)


def _validate_password(password: str) -> None:
    """检查密码复杂度：至少8位，包含字母、数字和特殊字符"""
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="密码长度至少8位")
    import re
    if not re.search(r'[A-Za-z]', password):
        raise HTTPException(status_code=400, detail="密码必须包含字母")
    if not re.search(r'\d', password):
        raise HTTPException(status_code=400, detail="密码必须包含数字")
    if not re.search(r'[^A-Za-z0-9]', password):
        raise HTTPException(status_code=400, detail="密码必须包含特殊字符")


def verify_password(plain: str, hashed: str) -> bool:
    if isinstance(hashed, str):
        hashed = hashed.encode('utf-8')
    return bcrypt.checkpw(plain.encode('utf-8'), hashed)


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


# 保留旧接口：密码派生 KEK，用于兼容历史数据解密回退
def _derive_kek(password: str, salt: str) -> bytes:
    from app.services.crypto import derive_key
    return derive_key(password, salt)


def _derive_recovery_kek(recovery_code: str, salt: str) -> bytes:
    from app.services.crypto import derive_key
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


def _hash_token(token: str) -> str:
    """SHA-256 摘要 refresh token，避免明文落库"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _cache_user_keys(user: User, password: str) -> None:
    """登录/注册时：解出主密钥并缓存到内存。

    新用户的主密钥由 KMS 包装；历史用户可能仍用密码派生 KEK 包装，
    此处先尝试 KMS 解包，失败再回退到 KEK 解包。
    """
    if not user.encryption_salt:
        user.encryption_salt = secrets.token_hex(16)

    # KEK 仍然派生并缓存，用于 session.py 中历史数据解密回退
    kek = _derive_kek(password, user.encryption_salt)

    if user.master_key_encrypted:
        master_key = None
        # 优先走 KMS 解包（新格式）
        try:
            master_key = kms.unwrap_master_key(user.master_key_encrypted)
        except Exception:
            pass
        if master_key is None:
            # 回退：历史数据用密码 KEK 包装
            from app.services.crypto import unwrap_master_key as _legacy_unwrap
            master_key = _legacy_unwrap(user.master_key_encrypted, kek)
    else:
        # 老用户首次登录无主密钥：经 KMS 生成
        master_key, encrypted = kms.generate_master_key_with_wrap()
        user.master_key_encrypted = encrypted

    key_manager.set_user_keys(user.id, kek, master_key)


def _rebuild_recovery_material(user: User, master_key: bytes, recovery_code: str) -> None:
    """用新的恢复码重新加密主密钥（备份路径，与 KMS 并存）"""
    from app.services.crypto import wrap_master_key as _legacy_wrap
    user.recovery_salt = secrets.token_hex(16)
    rkek = _derive_recovery_kek(recovery_code, user.recovery_salt)
    user.recovery_master_key_encrypted = _legacy_wrap(master_key, rkek)
    user.recovery_code_hash = _hash_recovery_code(recovery_code)


# ========== Token 签发与校验 ==========
def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    # jti 用于主动吊销（黑名单）
    to_encode.update({
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "type": "access",
    })
    return pyjwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    })
    return pyjwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def _persist_refresh_token(db: Session, user_id: str, token: str, request: Request) -> None:
    """把 refresh token 摘要写入数据库，支持后续吊销"""
    payload = pyjwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    db_token = RefreshToken(
        user_id=user_id,
        token_hash=_hash_token(token),
        user_agent=request.headers.get("user-agent", "")[:500] if request.headers.get("user-agent") else None,
        ip_address=request.client.host if request.client else None,
        expires_at=expires_at,
    )
    db.add(db_token)
    db.commit()


def _revoke_refresh_token(db: Session, token: str) -> bool:
    """吊销单个 refresh token"""
    token_hash = _hash_token(token)
    row = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked_at.is_(None),
    ).first()
    if row:
        row.revoked_at = _utc_now()
        db.commit()
        return True
    return False


def _revoke_all_refresh_tokens(db: Session, user_id: str) -> int:
    """吊销某用户全部有效 refresh token（改密码/登出全部设备时用）"""
    rows = db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked_at.is_(None),
    ).all()
    now = _utc_now()
    for r in rows:
        r.revoked_at = now
    db.commit()
    return len(rows)


def _extract_jti(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return ""
    try:
        payload = pyjwt.decode(auth[7:], settings.secret_key, algorithms=[settings.algorithm])
        return payload.get("jti", "")
    except Exception:
        return ""


from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
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
        # 拒绝 refresh token 被当作 access token 使用
        token_type = payload.get("type")
        if token_type and token_type != "access":
            raise credentials_exception
        # jti 黑名单校验
        jti = payload.get("jti")
        if jti and is_token_blacklisted(jti):
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception
    user = db.query(User).filter(User.phone == phone).first()
    if user is None:
        raise credentials_exception
    return user


# ========== 路由 ==========
@router.post("/register", response_model=Token, dependencies=[rate_limit(3, 300)])
def register(user: UserCreate, request: Request, db: Session = Depends(get_db)):
    try:
        existing = db.query(User).filter(User.phone == user.phone).first()
        if existing:
            raise HTTPException(status_code=400, detail="Phone already registered")

        _validate_password(user.password)

        user_id = str(uuid.uuid4())
        encryption_salt = secrets.token_hex(16)

        # 经 KMS 生成主密钥，明文只在内存中
        master_key, master_key_encrypted = kms.generate_master_key_with_wrap()

        # 恢复码备份包装（RKEK），用于 KMS 不可用时的应急恢复
        recovery_code = _generate_recovery_code()
        recovery_salt = secrets.token_hex(16)
        rkek = _derive_recovery_kek(recovery_code, recovery_salt)
        from app.services.crypto import wrap_master_key as _legacy_wrap
        recovery_master_key_encrypted = _legacy_wrap(master_key, rkek)

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

        # KEK 用于历史数据解密回退（新用户其实用不到，但保持接口一致）
        kek = _derive_kek(user.password, encryption_salt)
        key_manager.set_user_keys(db_user.id, kek, master_key)

        access_token = create_access_token({"sub": db_user.phone})
        refresh_token = create_refresh_token({"sub": db_user.phone})
        _persist_refresh_token(db, db_user.id, refresh_token, request)

        log_audit(
            db, actor_id=db_user.id, actor_role=db_user.role, action="register",
            resource_type="user", resource_id=db_user.id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            status_code=200,
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "recovery_code": recovery_code,
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger("cognitive_garden").error("Register failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="注册失败，请稍后重试")


@router.post("/login", response_model=Token, dependencies=[rate_limit(5, 300)])
def login(user: UserLogin, request: Request, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.phone == user.phone).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        log_audit(
            db, actor_role=None, action="login_failed",
            resource_type="user",
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            status_code=401,
            details={"phone": user.phone},
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    _cache_user_keys(db_user, user.password)
    db.commit()

    access_token = create_access_token({"sub": db_user.phone})
    refresh_token = create_refresh_token({"sub": db_user.phone})
    _persist_refresh_token(db, db_user.id, refresh_token, request)

    log_audit(
        db, actor_id=db_user.id, actor_role=db_user.role, action="login",
        resource_type="user", resource_id=db_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        status_code=200,
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/logout")
def logout(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """登出：吊销 refresh token + 黑名单 access token"""
    # 吊销当前请求携带的 refresh token（如有）
    auth = request.headers.get("Authorization", "")
    # 黑名单 access token 的 jti
    jti = _extract_jti(request)
    if jti:
        blacklist_token(jti, settings.access_token_expire_minutes * 60)

    # 吊销全部有效 refresh token（保守策略，单设备登出可改为只吊销当前 token）
    _revoke_all_refresh_tokens(db, current_user.id)

    key_manager.clear_user_key(current_user.id)

    log_audit(
        db, actor_id=current_user.id, actor_role=current_user.role, action="logout",
        resource_type="user", resource_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        status_code=200,
    )
    return {"detail": "已登出"}


@router.post("/refresh", response_model=Token, dependencies=[rate_limit(10, 300)])
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    """用 refresh token 换取新的 access + refresh token（轮换）"""
    try:
        decoded = pyjwt.decode(
            payload.refresh_token, settings.secret_key, algorithms=[settings.algorithm]
        )
        if decoded.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="无效的 refresh token")
        phone = decoded.get("sub")
        if not phone:
            raise HTTPException(status_code=401, detail="无效的 refresh token")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="refresh token 已过期或无效")

    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")

    # 校验数据库中是否仍有效（未被吊销）
    token_hash = _hash_token(payload.refresh_token)
    row = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked_at.is_(None),
        RefreshToken.expires_at > _utc_now(),
    ).first()
    if not row:
        raise HTTPException(status_code=401, detail="refresh token 已被吊销")

    # 轮换：吊销旧 refresh token，签发新对
    row.revoked_at = _utc_now()
    db.commit()

    access_token = create_access_token({"sub": user.phone})
    new_refresh = create_refresh_token({"sub": user.phone})
    _persist_refresh_token(db, user.id, new_refresh, request)

    return {
        "access_token": access_token,
        "refresh_token": new_refresh,
        "token_type": "bearer",
    }


@router.post("/recovery", dependencies=[rate_limit(3, 300)])
def recover_account(payload: RecoveryPayload, request: Request, db: Session = Depends(get_db)):
    """用恢复码重置密码。

    KMS 启用后主密钥不再依赖密码，但恢复码仍作为应急备份：
    通过 RKEK 解出主密钥 → 重新生成恢复码并重新包装。
    """
    user = db.query(User).filter(User.phone == payload.phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not user.recovery_code_hash or not user.recovery_master_key_encrypted or not user.recovery_salt:
        raise HTTPException(status_code=400, detail="该账户未设置恢复码")

    if not _verify_recovery_code(payload.recovery_code, user.recovery_code_hash):
        log_audit(
            db, actor_id=user.id, actor_role=user.role, action="recovery_failed",
            resource_type="user", resource_id=user.id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            status_code=401,
        )
        raise HTTPException(status_code=401, detail="恢复码不正确")

    try:
        # 通过恢复码解出主密钥（备份路径，独立于 KMS）
        from app.services.crypto import unwrap_master_key as _legacy_unwrap
        rkek = _derive_recovery_kek(payload.recovery_code, user.recovery_salt)
        master_key = _legacy_unwrap(user.recovery_master_key_encrypted, rkek)

        # 重置登录密码
        user.hashed_password = get_password_hash(payload.new_password)

        # 轮换恢复码
        new_recovery_code = _generate_recovery_code()
        _rebuild_recovery_material(user, master_key, new_recovery_code)

        # 吊销全部 refresh token（强制重新登录）
        _revoke_all_refresh_tokens(db, user.id)

        db.commit()
        key_manager.set_user_keys(user.id, _derive_kek(payload.new_password, user.encryption_salt), master_key)

        log_audit(
            db, actor_id=user.id, actor_role=user.role, action="recovery",
            resource_type="user", resource_id=user.id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            status_code=200,
        )

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
def change_password(
    payload: ChangePasswordPayload,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改登录密码。

    KMS 模式下：主密钥与密码解耦，仅需更新 bcrypt。
    历史用户（master_key 仍由 KEK 包装）：重新用新 KEK 包装主密钥。
    """
    if not verify_password(payload.old_password, current_user.hashed_password):
        raise HTTPException(status_code=401, detail="原密码不正确")

    _validate_password(payload.new_password)

    try:
        # 判断 master_key 是否已迁移到 KMS
        is_kms_wrapped = False
        try:
            kms.unwrap_master_key(current_user.master_key_encrypted)
            is_kms_wrapped = True
        except Exception:
            pass

        if not is_kms_wrapped:
            # 历史用户：用新密码 KEK 重新包装主密钥
            from app.services.crypto import wrap_master_key as _legacy_wrap
            master_key = key_manager.get_user_key(current_user.id)
            new_kek = _derive_kek(payload.new_password, current_user.encryption_salt)
            current_user.master_key_encrypted = _legacy_wrap(master_key, new_kek)
            key_manager.set_user_keys(current_user.id, new_kek, master_key)

        current_user.hashed_password = get_password_hash(payload.new_password)

        # 安全措施：吊销全部 refresh token + 黑名单当前 access token
        _revoke_all_refresh_tokens(db, current_user.id)
        jti = _extract_jti(request)
        if jti:
            blacklist_token(jti, settings.access_token_expire_minutes * 60)

        db.commit()

        log_audit(
            db, actor_id=current_user.id, actor_role=current_user.role, action="change_password",
            resource_type="user", resource_id=current_user.id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            status_code=200,
        )

        return {"detail": "密码修改成功，请重新登录"}
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
