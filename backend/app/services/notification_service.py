# ============ 家属端通知服务 ============
# 负责在图谱异常、衰退检测、量表到期等场景下生成通知
# 通知对象是家属，所以需要通过 FamilyLink 找到老人对应的家属
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from app.models import Notification, FamilyLink, ScaleRecord

logger = logging.getLogger("cognitive_garden")

# 量表到期提醒周期：每季度一次
_SCALE_REMINDER_INTERVAL_DAYS = 90


def _get_family_members_of(db: Session, elderly_user_id: str) -> List[FamilyLink]:
    """查出绑定这位老人的所有家属"""
    return db.query(FamilyLink).filter(FamilyLink.elderly_user_id == elderly_user_id).all()


def _severity_from_anomalies(anomalies: List[Dict[str, Any]]) -> str:
    """根据异常列表里最严重的等级，决定通知的 severity"""
    if not anomalies:
        return "info"
    severity_rank = {"info": 0, "warning": 1, "danger": 2}
    worst = "info"
    for a in anomalies:
        # 异常条目可能直接带 severity，也可能带 level，统一兼容
        sev = a.get("severity") or a.get("level") or "info"
        if sev not in severity_rank:
            sev = "info"
        if severity_rank[sev] > severity_rank[worst]:
            worst = sev
    return worst


def _create_for_family(
    db: Session,
    elderly_user_id: str,
    type_: str,
    title: str,
    content: str,
    severity: str,
    related_data: Optional[Dict[str, Any]] = None,
):
    """给老人绑定的所有家属批量写入一条通知，返回写入条数"""
    links = _get_family_members_of(db, elderly_user_id)
    if not links:
        # 没绑定家属，静默跳过；不算异常
        return 0

    for link in links:
        n = Notification(
            user_id=link.family_user_id,
            type=type_,
            title=title,
            content=content,
            severity=severity,
            related_data=related_data or {},
            is_read=False,
        )
        db.add(n)
    db.commit()
    return len(links)


def create_anomaly_notification(
    elderly_user_id: str,
    anomalies: List[Dict[str, Any]],
    db: Session,
    session_id: Optional[str] = None,
) -> int:
    """图谱出现异常时给家属发通知

    anomalies 是 NLP 管线产出的异常列表，每项形如
    {"event": "...", "severity": "warning", ...}
    """
    if not anomalies:
        return 0

    severity = _severity_from_anomalies(anomalies)
    # 标题里带上老人 id 的尾号，方便家属区分多位老人
    short_id = elderly_user_id[-4:] if elderly_user_id else ""
    title = "记忆图谱检测到异常"
    if short_id:
        title += f"（用户 #{short_id}）"

    # 内容里把每条异常的描述拼起来，超过 5 条折叠
    shown = anomalies[:5]
    lines = []
    for a in shown:
        ev = a.get("event") or a.get("type") or "异常"
        desc = a.get("description") or a.get("detail") or ""
        line = f"· {ev}"
        if desc:
            line += f"：{desc}"
        lines.append(line)
    if len(anomalies) > 5:
        lines.append(f"... 共 {len(anomalies)} 条异常")
    content = "\n".join(lines)

    related = {
        "elderly_user_id": elderly_user_id,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
    }
    if session_id:
        related["session_id"] = session_id

    return _create_for_family(db, elderly_user_id, "anomaly", title, content, severity, related)


def create_decline_notification(
    elderly_user_id: str,
    decline_data: Dict[str, Any],
    db: Session,
) -> int:
    """衰退检测出明显下降时给家属发通知

    decline_data 是 services/decline.py 的 analyze_narrative_diff 返回结构
    """
    score = decline_data.get("decline_score", 0)
    level = decline_data.get("level", "")
    # 数据不足或正常波动不推送，避免打扰家属
    if score < 20 or level in ("数据不足", "正常"):
        return 0

    if score >= 50:
        severity = "danger"
    else:
        severity = "warning"

    short_id = elderly_user_id[-4:] if elderly_user_id else ""
    title = "记忆衰退趋势提醒"
    if short_id:
        title += f"（用户 #{short_id}）"

    forgotten = decline_data.get("forgotten_entities", []) or []
    simplification = decline_data.get("narrative_simplification", {}) or {}
    repetition = decline_data.get("repetition", []) or []

    parts = [f"近 {decline_data.get('window_days', 7)} 天衰退分数 {score}（{level}）"]
    if forgotten:
        names = [f.get("entity", "") for f in forgotten[:3]]
        parts.append(f"遗忘实体：{', '.join(names)}" + (f" 等 {len(forgotten)} 个" if len(forgotten) > 3 else ""))
    if simplification:
        len_drop = simplification.get("sentence_len_drop", 0)
        den_drop = simplification.get("entity_density_drop", 0)
        if len_drop > 0 or den_drop > 0:
            parts.append(f"叙事简化：句长下降 {int(len_drop * 100)}%，密度下降 {int(den_drop * 100)}%")
    if repetition:
        parts.append(f"重复叙述 {len(repetition)} 处")
    content = "\n".join(parts)

    related = {
        "elderly_user_id": elderly_user_id,
        "decline_score": score,
        "level": level,
        "window_days": decline_data.get("window_days", 7),
    }

    return _create_for_family(db, elderly_user_id, "decline", title, content, severity, related)


def _ensure_utc(dt):
    """将 naive 或 aware datetime 统一转为 UTC aware"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def create_share_notification(elderly_user_id: str, family_user_id: str, session_id: str, db: Session) -> int:
    """老人分享会话给家属时，给家属发通知"""
    short_id = elderly_user_id[-4:] if elderly_user_id else ""
    title = "老人分享了新的记忆记录"
    if short_id:
        title += f"（用户 #{short_id}）"
    content = "老人分享了一条新的认知会话记录，点击查看详情。"
    related = {
        "elderly_user_id": elderly_user_id,
        "session_id": session_id,
        "type": "share",
    }
    n = Notification(
        user_id=family_user_id,
        type="share",
        title=title,
        content=content,
        severity="info",
        related_data=related,
        is_read=False,
    )
    db.add(n)
    db.commit()
    return 1


def create_scale_reminder(elderly_user_id: str, db: Session) -> int:
    """季度量表到期提醒：距上次量表评估超过 90 天就提醒一次"""
    # 找最近一次量表记录
    last = (
        db.query(ScaleRecord)
        .filter(ScaleRecord.user_id == elderly_user_id)
        .order_by(ScaleRecord.created_at.desc())
        .first()
    )
    now = datetime.now(timezone.utc)
    if last and last.created_at:
        last_created_at = _ensure_utc(last.created_at)
        days_since = (now - last_created_at).days
        if days_since < _SCALE_REMINDER_INTERVAL_DAYS:
            # 还没到期，不提醒
            return 0
        next_due = days_since - _SCALE_REMINDER_INTERVAL_DAYS
    else:
        # 从未做过量表，也提醒一次
        next_due = _SCALE_REMINDER_INTERVAL_DAYS

    short_id = elderly_user_id[-4:] if elderly_user_id else ""
    title = "认知量表到期提醒"
    if short_id:
        title += f"（用户 #{short_id}）"
    content = (
        f"距上次量表评估已超过 {_SCALE_REMINDER_INTERVAL_DAYS} 天，"
        "建议尽快安排一次 MMSE / AD8 复测，跟踪认知变化。"
    )
    related = {
        "elderly_user_id": elderly_user_id,
        "days_since_last": next_due,
        "interval_days": _SCALE_REMINDER_INTERVAL_DAYS,
    }
    return _create_for_family(db, elderly_user_id, "scale_reminder", title, content, "info", related)


def create_emotion_notification(
    elderly_user_id: str,
    latest_day: str,
    earliest_day: str,
    db: Session,
    session_id: Optional[str] = None,
) -> int:
    """连续 3 天消极情绪时给家属发通知"""
    short_id = elderly_user_id[-4:] if elderly_user_id else ""
    title = "情绪状态提醒：连续 3 天消极情绪"
    if short_id:
        title += f"（用户 #{short_id}）"
    content = (
        f"检测到老人在最近连续 3 天（{earliest_day} 至 {latest_day}）"
        "的情绪记录均为消极，建议关注老人的心理状态，适当陪伴或咨询专业意见。"
    )
    related = {
        "elderly_user_id": elderly_user_id,
        "consecutive_negative_days": 3,
        "start_day": earliest_day,
        "end_day": latest_day,
    }
    if session_id:
        related["session_id"] = session_id
    return _create_for_family(db, elderly_user_id, "emotion_alert", title, content, "warning", related)
