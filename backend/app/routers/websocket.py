"""WebSocket 实时通信路由：三端消息路由

消息格式: {from, to, type, payload, timestamp}
- type: family_care / doctor_advice / read_receipt / ping
"""
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.orm import Session
from jwt import InvalidTokenError
import jwt as pyjwt

from app.database import get_db
from app.models import User, FamilyLink, DoctorPatient
from app.config import get_settings
from app.services.connection_manager import manager

logger = logging.getLogger("cognitive_garden")
router = APIRouter(tags=["websocket"])
settings = get_settings()


def _verify_ws_token(token: str) -> dict:
    """验证 JWT token，返回 payload"""
    try:
        payload = pyjwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


async def _get_user_from_token(token: str, db: Session) -> User:
    payload = _verify_ws_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    """WebSocket 入口：query param ?token=JWT

    消息路由：
    - family -> elderly：家属发送语音留言/文字关怀，通过 WebSocket 推送到老人端
    - doctor -> elderly/family：医生发送诊断建议，推送到关联老人和家属
    - elderly -> family：老人端标记"已读"，推送到家属端
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    try:
        current_user = await _get_user_from_token(token, db)
    except HTTPException as e:
        await websocket.close(code=4001, reason=e.detail)
        return

    user_id = current_user.id
    role = current_user.role

    await manager.connect(user_id, websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"error": "Invalid JSON"}))
                continue

            msg_type = msg.get("type")
            to = msg.get("to")
            payload = msg.get("payload", {})
            ts = msg.get("timestamp") or datetime.now(timezone.utc).isoformat()

            # 自动补充 from 字段
            msg["from"] = user_id
            msg["timestamp"] = ts

            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "timestamp": ts}))
                continue

            if msg_type == "family_care":
                # 家属 -> 老人：检查绑定关系
                if role != "family":
                    await websocket.send_text(json.dumps({"error": "Only family can send care"}))
                    continue
                # 验证是否绑定了该老人
                link = (
                    db.query(FamilyLink)
                    .filter(
                        FamilyLink.family_user_id == user_id,
                        FamilyLink.elderly_user_id == to,
                        FamilyLink.is_active == True,
                    )
                    .first()
                )
                if not link:
                    await websocket.send_text(json.dumps({"error": "Not linked to this elderly"}))
                    continue
                await manager.send_to_user(to, msg)
                # 同时推送给其他绑定该老人的家属
                other_family = (
                    db.query(FamilyLink)
                    .filter(
                        FamilyLink.elderly_user_id == to,
                        FamilyLink.family_user_id != user_id,
                        FamilyLink.is_active == True,
                    )
                    .all()
                )
                for f in other_family:
                    await manager.send_to_user(f.family_user_id, msg)
                continue

            if msg_type == "doctor_advice":
                # 医生 -> 患者/家属
                if role != "doctor":
                    await websocket.send_text(json.dumps({"error": "Only doctor can send advice"}))
                    continue
                auth = (
                    db.query(DoctorPatient)
                    .filter(
                        DoctorPatient.doctor_id == user_id,
                        DoctorPatient.patient_id == to,
                        DoctorPatient.is_active == True,
                    )
                    .first()
                )
                if not auth:
                    await websocket.send_text(json.dumps({"error": "Not authorized for this patient"}))
                    continue
                # 推送给患者
                await manager.send_to_user(to, msg)
                # 推送给该患者的所有家属
                family_links = (
                    db.query(FamilyLink)
                    .filter(
                        FamilyLink.elderly_user_id == to,
                        FamilyLink.is_active == True,
                    )
                    .all()
                )
                for f in family_links:
                    await manager.send_to_user(f.family_user_id, msg)
                continue

            if msg_type == "read_receipt":
                # 老人 -> 家属：标记已读
                if role != "elderly":
                    await websocket.send_text(json.dumps({"error": "Only elderly can send read receipt"}))
                    continue
                # to 应该是 family_id
                link = (
                    db.query(FamilyLink)
                    .filter(
                        FamilyLink.elderly_user_id == user_id,
                        FamilyLink.family_user_id == to,
                        FamilyLink.is_active == True,
                    )
                    .first()
                )
                if not link:
                    await websocket.send_text(json.dumps({"error": "Not linked to this family"}))
                    continue
                await manager.send_to_user(to, msg)
                continue

            # 默认：直接转发给 to
            if to:
                await manager.send_to_user(to, msg)
            else:
                await websocket.send_text(json.dumps({"error": "Unknown message type or missing to"}))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WebSocket error for user %s: %s", user_id, e)
    finally:
        manager.disconnect(user_id, websocket)
        try:
            await websocket.close()
        except Exception:
            pass
