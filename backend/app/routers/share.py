"""分享路由：老人分享会话给家属，家属查看分享记录"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models import ShareRecord, User, FamilyLink, Session as DBSession
from app.routers.auth import get_current_user
from app.schemas import ShareCreate, ShareRecordOut
from app.services.notification_service import create_share_notification
import logging

logger = logging.getLogger("cognitive_garden")
router = APIRouter(prefix="/share", tags=["share"])


@router.post("/session/{session_id}", response_model=ShareRecordOut)
def share_session(
    session_id: str,
    payload: ShareCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """老人将某条会话分享给绑定的家属"""
    # 验证会话归属
    session = (
        db.query(DBSession)
        .filter(DBSession.id == session_id, DBSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 查找该老人绑定的家属（默认分享给第一个绑定的家属，或者可以扩展为多选）
    link = (
        db.query(FamilyLink)
        .filter(FamilyLink.elderly_user_id == current_user.id)
        .first()
    )
    if not link:
        raise HTTPException(status_code=400, detail="未绑定家属，无法分享")

    # 幂等：同一会话同一家属只保留一条分享记录
    existing = (
        db.query(ShareRecord)
        .filter(
            ShareRecord.session_id == session_id,
            ShareRecord.family_id == link.family_user_id,
        )
        .first()
    )
    if existing:
        return existing

    record = ShareRecord(
        session_id=session_id,
        elderly_id=current_user.id,
        family_id=link.family_user_id,
        message=payload.message,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # 给家属发通知
    try:
        create_share_notification(current_user.id, link.family_user_id, session_id, db)
    except Exception as e:
        logger.warning("发送分享通知失败: %s", e, exc_info=True)

    return record


@router.get("/", response_model=List[ShareRecordOut])
def list_share_records(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = 50,
):
    """家属查看老人分享给自己的记录；老人也能查看自己分享出去的记录"""
    if current_user.role == "family":
        records = (
            db.query(ShareRecord)
            .filter(ShareRecord.family_id == current_user.id)
            .order_by(ShareRecord.shared_at.desc())
            .limit(limit)
            .all()
        )
    else:
        records = (
            db.query(ShareRecord)
            .filter(ShareRecord.elderly_id == current_user.id)
            .order_by(ShareRecord.shared_at.desc())
            .limit(limit)
            .all()
        )
    return records
