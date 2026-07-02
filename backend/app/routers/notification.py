"""家属端通知路由：通知列表 / 已读 / 家属-老人绑定"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.models import Notification, FamilyLink, User
from app.routers.auth import get_current_user

router = APIRouter(prefix="/notification", tags=["notification"])


# ========== 请求/响应模型 ==========
class FamilyLinkCreate(BaseModel):
    elderly_username: str = Field(..., min_length=1, description="老人的手机号或姓名")
    relation: Optional[str] = Field(None, description="关系：子女/配偶/其他")


class FamilyMemberOut(BaseModel):
    link_id: str
    elderly_user_id: str
    elderly_name: Optional[str] = None
    elderly_phone: Optional[str] = None
    relation: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationOut(BaseModel):
    id: str
    user_id: str
    type: str
    title: str
    content: Optional[str] = None
    severity: str
    related_data: Optional[dict] = None
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ========== 通知相关 ==========
@router.get("/", response_model=List[NotificationOut])
def list_notifications(
    unread: Optional[bool] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的通知列表，按时间倒序，支持 ?unread=true 只看未读"""
    q = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread:
        q = q.filter(Notification.is_read.is_(False))
    return q.order_by(Notification.created_at.desc()).limit(limit).all()


@router.get("/unread-count")
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回当前用户的未读通知数量"""
    count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .count()
    )
    return {"unread_count": count}


@router.put("/{notification_id}/read")
def mark_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """标记单条通知为已读"""
    n = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )
    if not n:
        raise HTTPException(status_code=404, detail="通知不存在")
    if not n.is_read:
        n.is_read = True
        db.commit()
    return {"detail": "已标记已读", "id": notification_id}


@router.put("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """把当前用户的所有未读通知一次性标为已读"""
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .all()
    )
    for n in rows:
        n.is_read = True
    db.commit()
    return {"detail": "已全部标记已读", "updated": len(rows)}


# ========== 家属-老人绑定 ==========
def _find_elderly(db: Session, identifier: str) -> Optional[User]:
    """根据用户名、手机号或姓名找老人账号"""
    # username 优先
    user = db.query(User).filter(User.username == identifier).first()
    if user:
        return user
    # 手机号
    user = db.query(User).filter(User.phone == identifier).first()
    if user:
        return user
    # 姓名 fallback
    return db.query(User).filter(User.name == identifier).first()


@router.post("/family-link", response_model=FamilyMemberOut)
def link_family_member(
    payload: FamilyLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """家属通过老人的手机号或姓名建立关联"""
    elderly = _find_elderly(db, payload.elderly_username)
    if not elderly:
        raise HTTPException(status_code=404, detail="找不到该老人账号")

    if elderly.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能关联自己")

    existing = (
        db.query(FamilyLink)
        .filter(
            FamilyLink.elderly_user_id == elderly.id,
            FamilyLink.family_user_id == current_user.id,
        )
        .first()
    )
    if existing:
        if payload.relation and payload.relation != existing.relation:
            existing.relation = payload.relation
            db.commit()
            db.refresh(existing)
        return _to_family_member_out(existing)

    link = FamilyLink(
        elderly_user_id=elderly.id,
        family_user_id=current_user.id,
        relation=payload.relation,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return _to_family_member_out(link)


@router.get("/family-members", response_model=List[FamilyMemberOut])
def list_family_members(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前家属账号绑定的所有老人（使用 joinedload 避免 N+1）"""
    links = (
        db.query(FamilyLink)
        .options(joinedload(FamilyLink.elderly))
        .filter(FamilyLink.family_user_id == current_user.id)
        .order_by(FamilyLink.created_at.desc())
        .all()
    )
    return [_to_family_member_out(l) for l in links]


def _to_family_member_out(link: FamilyLink) -> FamilyMemberOut:
    """把 FamilyLink + 关联的 User 信息拼成响应"""
    return FamilyMemberOut(
        link_id=link.id,
        elderly_user_id=link.elderly_user_id,
        elderly_name=link.elderly.name if link.elderly else None,
        elderly_phone=link.elderly.phone if link.elderly else None,
        relation=link.relation,
        created_at=link.created_at,
    )
