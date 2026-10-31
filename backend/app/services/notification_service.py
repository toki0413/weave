# ============ 家属端通知服务 ============
# 负责在图谱异常、衰退检测、量表到期等场景下生成通知
# 通知对象是家属，所以需要通过 FamilyLink 找到老人对应的家属
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from app.models import Notification, FamilyLink, ScaleRecord
from app.models import Session as DBSession        # 会话表（本文件 Session 已被 ORM Session 占用）

logger = logging.getLogger("cognitive_garden")

# 量表到期提醒周期：每季度一次
_SCALE_REMINDER_INTERVAL_DAYS = 90

# 漏录判定按北京日历日切天，与 /notification/family-members 的 missing_days
# 及 pilot_export / weekly_baseline 的周桶同源（同一套偏移，避免 0–8 点歧义）
_LOCAL_TZ_OFFSET_MIN = 480

# ---- 告警频控与动作化（2026-10，DeCaAI 阴性结果教训：告警疲劳即弃用）----
# 同一信号 key 的冷却期（天）与家属端每日告警上限
_SIGNAL_COOLDOWN_DAYS = 3
_DAILY_ALERT_CAP = 2
# 被标记"误报"后的加长冷却期（闭环回填：误报信号自动降频）
_FALSE_ALARM_COOLDOWN_DAYS = 30

# 每类信号对应的家属可执行动作（每条告警必须附带"下一步做什么"）
_SIGNAL_ACTIONS: Dict[str, List[str]] = {
    "missed_checkin": [
        "打个电话或发条语音，问问今天做了什么——不用催 TA 打开应用",
        "若连续多日无记录，留意听力、情绪或操作是否遇到了困难",
    ],
    "entity_forgotten": [
        "翻看与 TA 相关的老照片或视频，温和地聊起这个人，不要考问",
        "下次复诊时把「最近较少提到 TA」告诉医生",
    ],
    "repetition": [
        "留意是否在重复问同一件事，记录发生的时间段",
        "带 TA 做一次该事件的「共同经历确认」，减少记忆固着带来的焦虑",
    ],
    "simplification": [
        "陪 TA 聊具体细节（何时、何地、和谁），鼓励每天多说一句",
        "检查听力/牙齿等影响表达意愿的生理因素",
    ],
    "anonymization": [
        "在 TA 用「那个谁」指代时，自然地帮 TA 补出名字，不要纠错",
    ],
    "anomaly": [
        "在 TA 提到这件事时自然确认是否记混；同月内多次出现再带去就诊",
    ],
    "emotion_negative": [
        "安排一次面对面的陪伴或视频通话",
        "连续一周消极时考虑寻求专业心理支持",
    ],
    "baseline_deviation": [
        "本周多安排一次共同活动，观察记录是否持续偏离",
        "保存本条告警，复诊时给医生看趋势而非单次数据",
    ],
}


def _actions_for(signal_key: str) -> List[str]:
    """按信号 key 前缀匹配家属动作建议"""
    for prefix, actions in _SIGNAL_ACTIONS.items():
        if signal_key.startswith(prefix):
            return actions
    return _SIGNAL_ACTIONS["anomaly"]


def _should_throttle(
    db: Session,
    family_user_id: str,
    type_: str,
    signal_key: str,
) -> bool:
    """告警频控：同一 signal_key 冷却期内不重发；误报标记后冷却期加长；
    高打扰类型（anomaly/decline）每家属每日上限 _DAILY_ALERT_CAP 条。

    返回 True 表示应跳过本次发送。
    """
    # missed_checkin 必须在此列表内：它的"同一天只发一条"靠的就是下面的
    # signal_key 冷却（key 里带北京日期）。此前该类型不在受控集合里，
    # 同一天重复执行任务会重复写通知。
    if type_ not in ("anomaly", "decline", "emotion_alert", "missed_checkin"):
        return False

    now = datetime.now(timezone.utc)

    # 每日上限
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = (
        db.query(Notification)
        .filter(
            Notification.user_id == family_user_id,
            Notification.type == type_,
            Notification.created_at >= day_start,
        )
        .count()
    )
    if today_count >= _DAILY_ALERT_CAP:
        return True

    # 信号级冷却
    recent = (
        db.query(Notification)
        .filter(
            Notification.user_id == family_user_id,
            Notification.type == type_,
        )
        .order_by(Notification.created_at.desc())
        .limit(20)
        .all()
    )
    for n in recent:
        data = n.related_data or {}
        if data.get("signal_key") != signal_key:
            continue
        created = _ensure_utc(n.created_at)
        if not created:
            continue
        cooldown = _SIGNAL_COOLDOWN_DAYS
        if (n.resolution_status or "pending") == "false_alarm":
            # 闭环回填：家属标记误报的信号降频
            cooldown = _FALSE_ALARM_COOLDOWN_DAYS
        if now - created < timedelta(days=cooldown):
            return True
    return False


def _get_family_members_of(db: Session, elderly_user_id: str) -> List[FamilyLink]:
    """查出绑定这位老人的所有家属"""
    return db.query(FamilyLink).filter(FamilyLink.elderly_user_id == elderly_user_id).all()


def _beijing_date(dt):
    """UTC → 北京日历日（与 family-members 的 missing_days、周桶同源）"""
    if dt is None:
        return None
    return (_ensure_utc(dt) + timedelta(minutes=_LOCAL_TZ_OFFSET_MIN)).date()


def compute_missing_days(db: Session, elderly_user_id: str, today=None):
    """老人距今几天没有新会话；从未记录返回 None（未知，不当成"漏了很多天"）"""
    last = (
        db.query(DBSession.created_at)
        .filter(DBSession.user_id == elderly_user_id)
        .order_by(DBSession.created_at.desc())
        .first()
    )
    if last is None or last[0] is None:
        return None
    today = today or datetime.now(timezone.utc)
    return max(0, (_beijing_date(today) - _beijing_date(last[0])).days)


def create_missed_checkin_notifications(db: Session, threshold_days: int = 2) -> int:
    """漏录日课提醒：连续 threshold_days 天没有新会话时提醒已绑定家属。

    幂等靠 signal_key 里的北京日期——同一天重复执行只有一条；且复用
    `_create_for_family` 的既有频控（冷却期 + 每日上限），不做骚扰式召回。
    从未记录的老人不推送（缺的是首次引导，不是催办）。
    """
    rows = db.query(FamilyLink.elderly_user_id).filter(
        FamilyLink.is_active == True).distinct().all()      # noqa: E712
    written = 0
    today_bj = _beijing_date(datetime.now(timezone.utc))
    for (elderly_id,) in rows:
        missing = compute_missing_days(db, elderly_id)
        if missing is None or missing < threshold_days:
            continue
        written += _create_for_family(
            db, elderly_id, "missed_checkin",
            title="今天还没有新的回忆",
            content=f"已经 {missing} 天没有听到 TA 的记录，找个安静的时间陪 TA 说说今天的事。",
            severity="warning",
            related_data={"missing_days": missing, "threshold_days": threshold_days},
            signal_key=f"missed_checkin|{today_bj}",
        )
    return written


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
    signal_key: Optional[str] = None,
    actions: Optional[List[str]] = None,
):
    """给老人绑定的所有家属批量写入一条通知，返回写入条数。

    带 signal_key 的高打扰类型（anomaly/decline/emotion_alert）逐家属做
    频控：冷却期内或超每日上限的家属跳过；每条通知附带可执行动作。
    """
    links = _get_family_members_of(db, elderly_user_id)
    if not links:
        # 没绑定家属，静默跳过；不算异常
        return 0

    related_data = related_data or {}
    if signal_key:
        related_data["signal_key"] = signal_key
    if actions is None and signal_key:
        actions = _actions_for(signal_key)
    if actions:
        related_data["actions"] = actions
        content = content + "\n建议：" + "；".join(actions[:2])

    written = 0
    for link in links:
        if signal_key and _should_throttle(db, link.family_user_id, type_, signal_key):
            continue
        n = Notification(
            user_id=link.family_user_id,
            type=type_,
            title=title,
            content=content,
            severity=severity,
            related_data=related_data,
            is_read=False,
        )
        db.add(n)
        written += 1
    if written:
        db.commit()
    return written


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

    # 信号 key：同组异常（按事件名排序）视为同一信号，做冷却频控
    event_names = sorted({a.get("event") or a.get("type") or "" for a in anomalies})
    signal_key = "anomaly|" + ",".join(event_names)[:120]

    return _create_for_family(
        db, elderly_user_id, "anomaly", title, content, severity, related,
        signal_key=signal_key,
    )


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
    signal_source = decline_data.get("signal_source", "fixed_threshold")
    if signal_source == "personal_baseline":
        parts.append("判定依据：相对 TA 自己的历史基线偏离（非群体固定阈值）")
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

    # 主信号维度决定动作建议与信号 key
    if forgotten:
        primary_signal = "entity_forgotten"
    elif repetition:
        primary_signal = "repetition"
    elif (simplification.get("sentence_len_drop", 0) > 0 or simplification.get("entity_density_drop", 0) > 0):
        primary_signal = "simplification"
    else:
        primary_signal = "baseline_deviation"
    signal_key = f"decline|{primary_signal}|{level}"

    related = {
        "elderly_user_id": elderly_user_id,
        "decline_score": score,
        "level": level,
        "window_days": decline_data.get("window_days", 7),
        "signal_source": signal_source,
    }

    return _create_for_family(
        db, elderly_user_id, "decline", title, content, severity, related,
        signal_key=signal_key,
    )


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
