"""离线同步协议：向量时钟 + 变更集 + 冲突解决

支持：
- pull_changes：获取服务器上自上次同步以来的所有变更
- push_changes：接收客户端变更，写入数据库，冲突时按规则解决
- resolve_conflict：LWW / doctor_priority / append
"""
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models import (
    User, Session as DBSession, ScaleRecord, VoiceMessage, DoctorPatient, DeviceSync, FamilyLink
)

logger = logging.getLogger("cognitive_garden")


def _utc_now():
    return datetime.now(timezone.utc)


def _get_device_sync(user_id: str, device_id: str, db: Session) -> DeviceSync:
    """获取或创建设备同步记录"""
    sync = (
        db.query(DeviceSync)
        .filter(DeviceSync.user_id == user_id, DeviceSync.device_id == device_id)
        .first()
    )
    if not sync:
        sync = DeviceSync(
            user_id=user_id,
            device_id=device_id,
            vector_clock={},
            last_sync_at=_utc_now(),
        )
        db.add(sync)
        db.commit()
        db.refresh(sync)
    return sync


def _increment_vector_clock(clock: dict, device_id: str) -> dict:
    """递增向量时钟中对应设备的时间戳"""
    clock = dict(clock) if clock else {}
    clock[device_id] = _utc_now().isoformat()
    return clock


def pull_changes(user_id: str, device_id: str, last_vector_clock: Optional[dict], db: Session):
    """拉取服务器上自上次同步以来的变更

    返回：
        {
            changes: {
                sessions: [...],
                scales: [...],
                voice_messages: [...],
                doctor_advices: [...]
            },
            server_vector_clock: {...}
        }
    """
    sync = _get_device_sync(user_id, device_id, db)
    last_sync_at = sync.last_sync_at

    # 如果客户端传了 last_vector_clock，尝试解析更精确的 last_sync_at
    if last_vector_clock and isinstance(last_vector_clock, dict):
        # 取所有设备时间戳的最小值作为保守下界
        times = [datetime.fromisoformat(t) for t in last_vector_clock.values() if isinstance(t, str)]
        if times:
            last_sync_at = min(times)

    changes = {
        "sessions": [],
        "scales": [],
        "voice_messages": [],
        "doctor_advices": [],
    }

    # 查询会话变更
    sessions = (
        db.query(DBSession)
        .filter(DBSession.user_id == user_id, DBSession.created_at > last_sync_at)
        .order_by(DBSession.created_at.desc())
        .all()
    )
    changes["sessions"] = [_session_to_dict(s) for s in sessions]

    # 查询量表变更
    scales = (
        db.query(ScaleRecord)
        .filter(ScaleRecord.user_id == user_id, ScaleRecord.created_at > last_sync_at)
        .order_by(ScaleRecord.created_at.desc())
        .all()
    )
    changes["scales"] = [_scale_to_dict(s) for s in scales]

    # 查询语音留言（作为接收者）
    vms = (
        db.query(VoiceMessage)
        .filter(VoiceMessage.receiver_id == user_id, VoiceMessage.created_at > last_sync_at)
        .order_by(VoiceMessage.created_at.desc())
        .all()
    )
    changes["voice_messages"] = [_vm_to_dict(v) for v in vms]

    # 更新 last_sync_at
    sync.last_sync_at = _utc_now()
    db.commit()

    # 构造全局向量时钟（取该用户所有设备的最大时间戳）
    all_syncs = db.query(DeviceSync).filter(DeviceSync.user_id == user_id).all()
    server_vector_clock = {}
    for s in all_syncs:
        if s.vector_clock:
            for dev, ts in s.vector_clock.items():
                if dev not in server_vector_clock or ts > server_vector_clock.get(dev, ""):
                    server_vector_clock[dev] = ts
    # 补充当前设备
    server_vector_clock[device_id] = sync.last_sync_at.isoformat()

    return {"changes": changes, "server_vector_clock": server_vector_clock}


def push_changes(user_id: str, device_id: str, changes: dict, db: Session):
    """接收客户端提交的变更，写入数据库，冲突时按规则解决

    changes 格式：
    {
        sessions: [{...}],
        scales: [{...}],
        voice_messages: [{...}]
    }

    返回：
        {conflicts: [...], new_vector_clock: {...}}
    """
    conflicts = []
    sync = _get_device_sync(user_id, device_id, db)

    # 处理会话变更
    for item in changes.get("sessions", []):
        conflict = _apply_session_change(user_id, item, db)
        if conflict:
            conflicts.append(conflict)

    # 处理量表变更
    for item in changes.get("scales", []):
        conflict = _apply_scale_change(user_id, item, db)
        if conflict:
            conflicts.append(conflict)

    # 处理语音留言
    for item in changes.get("voice_messages", []):
        conflict = _apply_voice_message_change(user_id, item, db)
        if conflict:
            conflicts.append(conflict)

    # 更新向量时钟
    sync.vector_clock = _increment_vector_clock(sync.vector_clock, device_id)
    sync.last_sync_at = _utc_now()
    db.commit()

    return {
        "conflicts": conflicts,
        "new_vector_clock": sync.vector_clock,
    }


def resolve_conflict(local_data: dict, server_data: dict, rule: str = "lww") -> dict:
    """冲突解决策略

    - lww: Last Write Wins，以 updated_at 较晚的为准
    - doctor_priority: 医生端数据始终优先
    - append: 语音留言等独立队列，双向追加
    """
    if rule == "append":
        # 语音留言独立追加，不冲突
        return {**local_data, "_merged": True, "_rule": "append"}

    if rule == "doctor_priority":
        # 医生端数据优先（假设 doctor_data 标记为 source_role=doctor）
        local_role = local_data.get("source_role", "")
        server_role = server_data.get("source_role", "")
        if server_role == "doctor" and local_role != "doctor":
            return {**server_data, "_merged": True, "_rule": "doctor_priority"}
        if local_role == "doctor" and server_role != "doctor":
            return {**local_data, "_merged": True, "_rule": "doctor_priority"}
        # 都不是医生，回退到 lww
        rule = "lww"

    if rule == "lww":
        local_ts = local_data.get("updated_at") or local_data.get("created_at") or ""
        server_ts = server_data.get("updated_at") or server_data.get("created_at") or ""
        if server_ts >= local_ts:
            return {**server_data, "_merged": True, "_rule": "lww", "_winner": "server"}
        else:
            return {**local_data, "_merged": True, "_rule": "lww", "_winner": "local"}

    # 默认返回服务器数据
    return {**server_data, "_merged": True, "_rule": "default", "_winner": "server"}


# ---------- 内部辅助函数 ----------

def _session_to_dict(s: DBSession) -> dict:
    return {
        "id": s.id,
        "user_id": s.user_id,
        "day_number": s.day_number,
        "narrative": s.narrative,
        "graph": s.graph,
        "metrics": s.metrics,
        "health_score": s.health_score,
        "anomalies": s.anomalies,
        "emotion_score": s.emotion_score,
        "emotion_label": s.emotion_label,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _scale_to_dict(s: ScaleRecord) -> dict:
    return {
        "id": s.id,
        "user_id": s.user_id,
        "scale_type": s.scale_type,
        "answers": s.answers,
        "total_score": s.total_score,
        "interpretation": s.interpretation,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _vm_to_dict(v: VoiceMessage) -> dict:
    return {
        "id": v.id,
        "sender_id": v.sender_id,
        "receiver_id": v.receiver_id,
        "audio_url": v.audio_url,
        "duration": v.duration,
        "is_read": v.is_read,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


def _apply_session_change(user_id: str, item: dict, db: Session) -> Optional[dict]:
    """应用客户端会话变更，冲突返回 conflict 描述"""
    existing = db.query(DBSession).filter(DBSession.id == item.get("id")).first()
    if not existing:
        # 新建
        s = DBSession(
            id=item.get("id"),
            user_id=user_id,
            day_number=item.get("day_number", 1),
            narrative=item.get("narrative", ""),
            graph=item.get("graph"),
            metrics=item.get("metrics"),
            health_score=item.get("health_score"),
            anomalies=item.get("anomalies"),
            emotion_score=item.get("emotion_score"),
            emotion_label=item.get("emotion_label"),
        )
        db.add(s)
        return None
    # 冲突检测：以 created_at 为代理（会话通常不更新）
    local_ts = item.get("created_at", "")
    server_ts = existing.created_at.isoformat() if existing.created_at else ""
    if local_ts != server_ts:
        winner = resolve_conflict(item, _session_to_dict(existing), rule="lww")
        if winner.get("_winner") == "server":
            return {"type": "session", "id": existing.id, "resolution": "server_kept", "reason": "lww"}
        # 覆盖
        existing.narrative = item.get("narrative", existing.narrative)
        existing.graph = item.get("graph", existing.graph)
        existing.metrics = item.get("metrics", existing.metrics)
        existing.health_score = item.get("health_score", existing.health_score)
    return None


def _apply_scale_change(user_id: str, item: dict, db: Session) -> Optional[dict]:
    existing = db.query(ScaleRecord).filter(ScaleRecord.id == item.get("id")).first()
    if not existing:
        s = ScaleRecord(
            id=item.get("id"),
            user_id=user_id,
            scale_type=item.get("scale_type", ""),
            answers=item.get("answers"),
            total_score=item.get("total_score", 0),
            interpretation=item.get("interpretation", ""),
            is_encrypted=item.get("is_encrypted", False),
        )
        db.add(s)
        return None
    local_ts = item.get("created_at", "")
    server_ts = existing.created_at.isoformat() if existing.created_at else ""
    if local_ts != server_ts:
        winner = resolve_conflict(item, _scale_to_dict(existing), rule="lww")
        if winner.get("_winner") == "server":
            return {"type": "scale", "id": existing.id, "resolution": "server_kept", "reason": "lww"}
        existing.answers = item.get("answers", existing.answers)
        existing.total_score = item.get("total_score", existing.total_score)
    return None


def _apply_voice_message_change(user_id: str, item: dict, db: Session) -> Optional[dict]:
    existing = db.query(VoiceMessage).filter(VoiceMessage.id == item.get("id")).first()
    if not existing:
        v = VoiceMessage(
            id=item.get("id"),
            sender_id=item.get("sender_id", user_id),
            receiver_id=item.get("receiver_id", ""),
            audio_url=item.get("audio_url", ""),
            duration=item.get("duration", 0),
            is_read=item.get("is_read", False),
        )
        db.add(v)
        return None
    # 语音留言使用 append 规则：允许两端都有同一条记录，不覆盖
    return {"type": "voice_message", "id": existing.id, "resolution": "append", "reason": "append_rule"}
