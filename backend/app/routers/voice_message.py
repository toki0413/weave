"""语音留言路由：上传、列表、标记已读"""
import base64
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models import VoiceMessage, User, FamilyLink
from app.routers.auth import get_current_user
from app.services.e2ee import encrypt_for_recipient
from app.services import key_manager
from app.middleware.permission import filter_by_permission
from app.schemas import VoiceMessageCreate, VoiceMessageOut

router = APIRouter(prefix="/voice-message", tags=["voice-message"])

# 确保上传目录存在
UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _utc_now():
    return datetime.now(timezone.utc)


@router.post("/", response_model=VoiceMessageOut)
def create_voice_message(
    payload: VoiceMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传语音留言：base64 音频解码后存入文件系统，数据库存路径"""
    # 验证接收者是否为当前用户绑定的老人/家属
    link = (
        db.query(FamilyLink)
        .filter(
            ((FamilyLink.elderly_user_id == current_user.id) & (FamilyLink.family_user_id == payload.receiver_id))
            | ((FamilyLink.family_user_id == current_user.id) & (FamilyLink.elderly_user_id == payload.receiver_id))
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=403, detail="只能给绑定的家属或老人发送语音留言")

    # 解码 base64 音频（兼容 data URL 前缀和缺少 padding 的情况）
    try:
        b64_data = payload.audio_base64
        if "," in b64_data and b64_data.startswith("data:"):
            b64_data = b64_data.split(",", 1)[1]
        # 补齐 padding（base64 长度必须是 4 的倍数）
        padding = len(b64_data) % 4
        if padding:
            b64_data += "=" * (4 - padding)
        audio_bytes = base64.b64decode(b64_data)
    except Exception:
        raise HTTPException(status_code=400, detail="无效的 base64 音频数据")

    if len(audio_bytes) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="音频文件过大，限制 50MB")

    # 端到端加密：用发送方主密钥 + 接收方 ID 派生共享密钥
    try:
        master_key = key_manager.get_user_key(current_user.id)
    except RuntimeError:
        raise HTTPException(status_code=401, detail="加密密钥不可用，请重新登录")

    encrypted = encrypt_for_recipient(payload.audio_base64, master_key, payload.receiver_id)
    encrypted_json = json.dumps(encrypted)
    encrypted_bytes = encrypted_json.encode("utf-8")

    # 保存加密后的音频数据到文件系统
    ext = "enc.json"  # 加密后的 JSON 格式
    filename = f"voice_{uuid.uuid4().hex}.{ext}"
    file_path = UPLOAD_DIR / filename
    file_path.write_bytes(encrypted_bytes)

    db_msg = VoiceMessage(
        sender_id=current_user.id,
        receiver_id=payload.receiver_id,
        audio_url=f"/uploads/{filename}",
        duration=payload.duration,
        created_at=_utc_now(),
        is_read=False,
    )
    db.add(db_msg)
    db.commit()
    db.refresh(db_msg)

    # 返回时附带密文，前端可直接解密
    db_msg.encrypted_payload = encrypted
    return db_msg


@router.get("/", response_model=List[VoiceMessageOut])
def list_voice_messages(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = 50,
):
    """获取当前用户收到或发送的语音留言列表，按时间倒序"""
    from app.middleware.permission import filter_by_permission
    query = db.query(VoiceMessage)
    query = filter_by_permission(query, current_user, db)
    messages = query.order_by(VoiceMessage.created_at.desc()).limit(limit).all()

    # 为每条消息读取加密 payload
    for msg in messages:
        if msg.audio_url and msg.audio_url.endswith(".enc.json"):
            try:
                enc_path = UPLOAD_DIR / msg.audio_url.replace("/uploads/", "")
                if enc_path.exists():
                    with open(enc_path, "r", encoding="utf-8") as f:
                        msg.encrypted_payload = json.load(f)
            except Exception:
                msg.encrypted_payload = None
        else:
            msg.encrypted_payload = None

    return messages


@router.post("/{message_id}/mark-read")
def mark_voice_message_read(
    message_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """标记语音留言为已读"""
    msg = (
        db.query(VoiceMessage)
        .filter(VoiceMessage.id == message_id, VoiceMessage.receiver_id == current_user.id)
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="语音留言不存在")
    if not msg.is_read:
        msg.is_read = True
        db.commit()
    return {"detail": "已标记已读", "id": message_id}
