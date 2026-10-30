"""家属端通知路由：通知列表 / 已读 / 家属-老人绑定"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime, timezone

from app.database import get_db
from app.models import Notification, FamilyLink, User, Session as DBSession
from app.routers.auth import get_current_user

router = APIRouter(prefix="/notification", tags=["notification"])

# 漏录天数按本地日历日切天（UTC+8），与 pilot_export / weekly_baseline 同源
_LOCAL_TZ_OFFSET_MIN = 480


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
    # 漏录提醒数据源（audit-24）：最近一条会话与"距今几天没记录"。
    # 无会话时两者为 None——UI 显示"还没有记录"而不是"漏了 N 天"
    last_session_at: Optional[datetime] = None
    missing_days: Optional[int] = None

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
    resolution_status: Optional[str] = "pending"
    resolution_note: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationResolve(BaseModel):
    """告警处理回填：闭环「告警 → 家属处理 → 结果 → 基线修正」"""
    status: str = Field(..., description="handled / helpful / not_helpful / false_alarm")
    note: Optional[str] = Field(None, max_length=500, description="处理说明（可选）")


class NotificationSummary(BaseModel):
    total: int
    pending: int
    handled: int
    false_alarm: int
    by_severity: dict


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


_VALID_RESOLUTIONS = {"handled", "helpful", "not_helpful", "false_alarm"}


@router.put("/{notification_id}/resolve")
def resolve_notification(
    notification_id: str,
    payload: NotificationResolve,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """回填告警处理结果（闭环第三步）。

    false_alarm 会通知服务层对该 signal_key 降频 30 天（基线修正 v1）。
    """
    if payload.status not in _VALID_RESOLUTIONS:
        raise HTTPException(status_code=400, detail=f"status 必须是 {'/'.join(sorted(_VALID_RESOLUTIONS))}")
    n = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )
    if not n:
        raise HTTPException(status_code=404, detail="通知不存在")
    n.resolution_status = payload.status
    n.resolution_note = payload.note
    n.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "detail": "已回填处理结果",
        "id": notification_id,
        "resolution_status": n.resolution_status,
        # 前端据此提示「同类告警将暂缓推送」
        "signal_suppressed": payload.status == "false_alarm" and bool((n.related_data or {}).get("signal_key")),
    }


@router.get("/summary", response_model=NotificationSummary)
def notification_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """照护视图：按处理状态与严重度聚合当前用户的告警"""
    rows = db.query(Notification).filter(Notification.user_id == current_user.id).all()
    by_severity: dict = {"info": 0, "warning": 0, "danger": 0}
    pending = handled = false_alarm = 0
    for n in rows:
        sev = n.severity if n.severity in by_severity else "info"
        by_severity[sev] += 1
        status = n.resolution_status or "pending"
        if status == "pending":
            pending += 1
        elif status == "false_alarm":
            false_alarm += 1
        else:
            handled += 1
    return NotificationSummary(
        total=len(rows), pending=pending, handled=handled,
        false_alarm=false_alarm, by_severity=by_severity,
    )


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
        return _to_family_member_out(db, existing)

    link = FamilyLink(
        elderly_user_id=elderly.id,
        family_user_id=current_user.id,
        relation=payload.relation,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return _to_family_member_out(db, link)


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
    return [_to_family_member_out(db, l) for l in links]


def _to_family_member_out(db: Session, link: FamilyLink) -> FamilyMemberOut:
    """把 FamilyLink + 关联的 User 信息拼成响应，并附最近记录/漏录天数。

    漏录天数按本地日历日（UTC+8）切天，与 pilot_export / weekly_baseline 的
    周桶同源——否则 0:00–8:00 之间录的会被算成漏一天。只算"有没有录"，
    不做质量判断。
    """
    last = (
        db.query(DBSession.created_at)
        .filter(DBSession.user_id == link.elderly_user_id)
        .order_by(DBSession.created_at.desc())
        .first()
    )
    last_at = last[0] if last else None
    missing_days = None
    if last_at is not None:
        from datetime import timedelta
        loc_last = (last_at + timedelta(minutes=_LOCAL_TZ_OFFSET_MIN)).date()
        loc_now = (datetime.now(timezone.utc) + timedelta(minutes=_LOCAL_TZ_OFFSET_MIN)).date()
        missing_days = max(0, (loc_now - loc_last).days)
    return FamilyMemberOut(
        link_id=link.id,
        elderly_user_id=link.elderly_user_id,
        elderly_name=link.elderly.name if link.elderly else None,
        elderly_phone=link.elderly.phone if link.elderly else None,
        relation=link.relation,
        created_at=link.created_at,
        last_session_at=last_at,
        missing_days=missing_days,
    )
