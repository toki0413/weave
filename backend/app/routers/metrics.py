"""产品分析路由：事件埋点上报 + 研究漏斗聚合

工程债背景（2026-10）：此前产品零埋点，日课完成率、告警误报率等研究
指标无法统计。隐私红线：本表只存事件名+轻量属性，禁止叙事文本/健康数据。

权限：事件上报需登录；聚合端点仅 doctor 角色可用（本系统三角色中
doctor 即研究/临床侧的代理角色）。
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AnalyticsEvent, User, Session as DBSession, Notification
from app.routers.auth import get_current_user
from app.routers.session import rate_limit
from app.schemas import (
    AnalyticsEventBatch,
    ResearchSummary,
    DailyPromptFunnel,
    AlertFunnel,
)

logger = logging.getLogger("cognitive_garden")

router = APIRouter(prefix="/metrics", tags=["analytics"])

# 漏斗统计的事件名白名单（上报不做白名单限制，聚合只看这些）
_FUNNEL_EVENTS = {
    "daily_prompt_exposed",
    "daily_prompt_filled",
    "daily_prompt_submitted",
}


@router.post("/events", dependencies=[rate_limit(30, 60)])
def report_events(
    batch: AnalyticsEventBatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量上报埋点事件（≤50 条/批）。失败静默：埋点绝不阻塞主流程。"""
    now = datetime.now(timezone.utc)
    rows = []
    for ev in batch.events:
        props = ev.properties
        # 属性体积红线：序列化后 >1KB 直接丢弃属性只留事件名
        if props and len(str(props)) > 1024:
            props = {"_truncated": True}
        rows.append(AnalyticsEvent(
            user_id=current_user.id,
            event_name=ev.name,
            properties=props,
            client_ts=ev.client_ts,
        ))
    if rows:
        db.add_all(rows)
        db.commit()
    return {"accepted": len(rows)}


# 匿名埋点白名单：仅增长归因类事件（分享落地/注册归因），无用户态
_PUBLIC_EVENT_WHITELIST = {"landing_viewed", "register_from_share"}


@router.post("/events/public", dependencies=[rate_limit(10, 60)])
def report_public_events(
    batch: AnalyticsEventBatch,
    db: Session = Depends(get_db),
):
    """免登录埋点：分享卡片访客落地与注册归因（K 因子度量）。

    只收白名单事件名，属性 >512B 丢弃；user_id 恒为 NULL。
    """
    rows = []
    for ev in batch.events:
        if ev.name not in _PUBLIC_EVENT_WHITELIST:
            continue
        props = ev.properties
        if props and len(str(props)) > 512:
            props = {"_truncated": True}
        rows.append(AnalyticsEvent(
            user_id=None,
            event_name=ev.name,
            properties=props,
            client_ts=ev.client_ts,
        ))
    if rows:
        db.add_all(rows)
        db.commit()
    return {"accepted": len(rows)}


def _pct(num: int, den: int):
    return round(num / den, 4) if den > 0 else None


@router.get("/research/summary", response_model=ResearchSummary)
def research_summary(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """研究漏斗聚合（仅 doctor 角色）。

    - 日课漏斗：exposed → filled → submitted（sessions.source=daily_prompt）
    - 告警漏斗：created → resolved → false_alarm 率
    """
    if (current_user.role or "") != "doctor":
        raise HTTPException(status_code=403, detail="仅 doctor 角色可查看研究聚合")

    days = max(1, min(days, 180))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    events = (
        db.query(AnalyticsEvent)
        .filter(AnalyticsEvent.created_at >= since, AnalyticsEvent.event_name.in_(_FUNNEL_EVENTS))
        .all()
    )
    counts = {name: 0 for name in _FUNNEL_EVENTS}
    event_users = set()
    all_users: set = set()
    for e in events:
        counts[e.event_name] += 1
        event_users.add(e.user_id)
        all_users.add(e.user_id)

    # 日课提交：以 sessions.source 归因（比前端埋点更可靠）
    submitted = (
        db.query(DBSession)
        .filter(DBSession.source == "daily_prompt", DBSession.created_at >= since)
        .count()
    )
    submitted_users = (
        db.query(DBSession.user_id)
        .filter(DBSession.source == "daily_prompt", DBSession.created_at >= since)
        .distinct()
        .all()
    )
    all_users |= {u[0] for u in submitted_users}

    # 活跃用户：窗口内有任何分析事件或提交会话的用户
    any_event_users = (
        db.query(AnalyticsEvent.user_id)
        .filter(AnalyticsEvent.created_at >= since)
        .distinct()
        .all()
    )
    all_users |= {u[0] for u in any_event_users}

    session_users = (
        db.query(DBSession.user_id)
        .filter(DBSession.created_at >= since)
        .distinct()
        .all()
    )
    all_users |= {u[0] for u in session_users}

    # 告警漏斗
    alert_q = db.query(Notification).filter(Notification.type.in_(["anomaly", "decline"]))
    # Notification 无 created_at 过滤便捷字段名差异，直接在 Python 侧过滤时间
    alerts = [n for n in alert_q.all() if n.created_at and _ensure_utc(n.created_at) >= since]
    resolved = sum(1 for n in alerts if (n.resolution_status or "pending") != "pending")
    false_alarm = sum(1 for n in alerts if n.resolution_status == "false_alarm")

    return ResearchSummary(
        days=days,
        active_users=len(all_users),
        daily_prompt=DailyPromptFunnel(
            exposed=counts["daily_prompt_exposed"],
            filled=counts["daily_prompt_filled"],
            submitted=submitted,
            fill_rate=_pct(counts["daily_prompt_filled"], counts["daily_prompt_exposed"]),
            submit_rate=_pct(submitted, counts["daily_prompt_filled"]),
        ),
        alerts=AlertFunnel(
            created=len(alerts),
            resolved=resolved,
            false_alarm=false_alarm,
            false_alarm_rate=_pct(false_alarm, len(alerts)),
        ),
    )


def _ensure_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
