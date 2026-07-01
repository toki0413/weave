# ============ 记忆衰退分析服务 ============
# 对比用户近期与历史叙事，检测实体遗忘、叙事简化、重复叙述、匿名化上升
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

from sqlalchemy.orm import Session

from app.models import Session as DBSession
from app.services.baseline_personal import (
    check_personal_deviation,
    get_baseline_explanation,
)
from app.services.nlp import extract_entities, extract_anon_features

logger = logging.getLogger("cognitive_garden")

# 句子分隔符：句号/问号/感叹号/分号/换行
_SENT_SPLIT = re.compile(r"[。！？；\n]+")


def _split_sentences(text: str) -> List[str]:
    """切句，过滤空串"""
    if not text:
        return []
    return [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]


def _avg_sentence_len(text: str) -> float:
    """平均句子长度（字符数）"""
    sents = _split_sentences(text)
    if not sents:
        return 0.0
    return sum(len(s) for s in sents) / len(sents)


def _entity_density(text: str, entities: Dict[str, List[str]]) -> float:
    """实体密度：每百字实体数（去重）"""
    if not text:
        return 0.0
    total = sum(len(v) for v in entities.values())
    return total * 100.0 / max(len(text), 1)


def _flatten_entities(entities: Dict[str, List[str]]) -> List[str]:
    """把 entities dict 拍平成实体列表"""
    out = []
    for v in entities.values():
        out.extend(v)
    return out


def _collect_session_stats(sessions: List[DBSession]) -> Dict[str, Any]:
    """汇总一段时间窗口内的会话统计"""
    all_entities: List[str] = []
    entity_freq: Dict[str, int] = defaultdict(int)
    total_chars = 0
    total_sents = 0
    total_entities = 0
    anon_count = 0
    sentence_lens: List[float] = []
    densities: List[float] = []
    event_freq: Dict[str, int] = defaultdict(int)
    per_day_events: List[set] = []

    for s in sessions:
        text = s.narrative or ""
        if not text.strip():
            continue
        ents = extract_entities(text)
        flat = _flatten_entities(ents)
        all_entities.extend(flat)
        for e in flat:
            entity_freq[e] += 1
        for ev in ents.get("events", []):
            event_freq[ev] += 1
        sents = _split_sentences(text)
        total_sents += len(sents)
        total_chars += len(text)
        total_entities += len(flat)
        anon_count += len(extract_anon_features(text))
        sentence_lens.append(_avg_sentence_len(text))
        densities.append(_entity_density(text, ents))
        per_day_events.append(set(ents.get("events", [])))

    avg_sent_len = sum(sentence_lens) / len(sentence_lens) if sentence_lens else 0.0
    avg_density = sum(densities) / len(densities) if densities else 0.0
    anon_ratio = anon_count / max(len(sessions), 1)

    return {
        "session_count": len(sessions),
        "entity_freq": dict(entity_freq),
        "event_freq": dict(event_freq),
        "all_entities": all_entities,
        "total_chars": total_chars,
        "total_sents": total_sents,
        "total_entities": total_entities,
        "anon_count": anon_count,
        "anon_ratio": anon_ratio,
        "avg_sentence_len": avg_sent_len,
        "avg_entity_density": avg_density,
        "per_day_events": per_day_events,
    }


def _detect_forgotten_entities(
    recent: Dict[str, Any],
    previous: Dict[str, Any],
    recent_window_days: int,
) -> List[Dict[str, Any]]:
    """实体遗忘：之前出现但近期未再提及"""
    prev_entities = set(previous["entity_freq"].keys())
    recent_entities = set(recent["entity_freq"].keys())
    forgotten = prev_entities - recent_entities
    # 只保留之前至少出现过一次的实体，避免噪声
    result = []
    for e in forgotten:
        prev_count = previous["entity_freq"].get(e, 0)
        if prev_count < 1:
            continue
        result.append({
            "entity": e,
            "previous_count": prev_count,
            "days_absent": recent_window_days,
        })
    # 按之前出现次数降序
    result.sort(key=lambda x: x["previous_count"], reverse=True)
    return result


def _detect_narrative_simplification(
    recent: Dict[str, Any],
    previous: Dict[str, Any],
) -> Dict[str, Any]:
    """叙事简化：句子平均长度、实体密度下降"""
    prev_len = previous["avg_sentence_len"]
    rec_len = recent["avg_sentence_len"]
    prev_den = previous["avg_entity_density"]
    rec_den = recent["avg_entity_density"]

    # 下降比例（正数表示下降，负数表示上升）
    len_drop = (prev_len - rec_len) / prev_len if prev_len > 0 else 0.0
    den_drop = (prev_den - rec_den) / prev_den if prev_den > 0 else 0.0

    return {
        "prev_avg_sentence_len": round(prev_len, 2),
        "recent_avg_sentence_len": round(rec_len, 2),
        "sentence_len_drop": round(len_drop, 3),
        "prev_entity_density": round(prev_den, 2),
        "recent_entity_density": round(rec_den, 2),
        "entity_density_drop": round(den_drop, 3),
    }


def _detect_repetition(recent: Dict[str, Any], threshold: int = 3) -> List[Dict[str, Any]]:
    """重复叙述：同一事件在多个不同会话日反复出现（记忆固着信号）"""
    if not recent["per_day_events"]:
        return []
    event_day_count: Dict[str, int] = defaultdict(int)
    for day_set in recent["per_day_events"]:
        for ev in day_set:
            event_day_count[ev] += 1
    result = []
    for ev, cnt in event_day_count.items():
        if cnt >= threshold:
            result.append({
                "event": ev,
                "consecutive_days": cnt,
            })
    result.sort(key=lambda x: x["consecutive_days"], reverse=True)
    return result


def _detect_anonymization_trend(
    recent: Dict[str, Any],
    previous: Dict[str, Any],
) -> Dict[str, Any]:
    """匿名化趋势：匿名节点比例上升"""
    prev_ratio = previous["anon_ratio"]
    rec_ratio = recent["anon_ratio"]
    rise = rec_ratio - prev_ratio
    rise_pct = rise / prev_ratio if prev_ratio > 0 else (1.0 if rec_ratio > 0 else 0.0)
    return {
        "prev_anon_ratio": round(prev_ratio, 3),
        "recent_anon_ratio": round(rec_ratio, 3),
        "rise": round(rise, 3),
        "rise_pct": round(rise_pct, 3),
    }


def _compute_decline_score(
    forgotten: List[Dict[str, Any]],
    simplification: Dict[str, Any],
    repetition: List[Dict[str, Any]],
    anon_trend: Dict[str, Any],
) -> Tuple[int, str]:
    """综合衰退分数：0-100，越高越严重；返回 (score, level)"""
    score = 0

    # 1) 实体遗忘：每遗忘 1 个加 6 分，最多 40
    forgotten_score = min(40, len(forgotten) * 6)
    score += forgotten_score

    # 2) 叙事简化：句子长度下降 + 实体密度下降，各最多 20
    len_drop = max(0.0, simplification.get("sentence_len_drop", 0))
    den_drop = max(0.0, simplification.get("entity_density_drop", 0))
    score += min(20, int(len_drop * 40))
    score += min(20, int(den_drop * 40))

    # 3) 重复叙述：每条加 5 分，最多 15
    score += min(15, len(repetition) * 5)

    # 4) 匿名化上升：rise_pct > 0.2 视为显著，加 5~15
    rise_pct = anon_trend.get("rise_pct", 0)
    if rise_pct > 0.5:
        score += 15
    elif rise_pct > 0.2:
        score += 10
    elif rise_pct > 0:
        score += 5

    score = max(0, min(100, score))
    if score < 20:
        level = "正常"
    elif score < 50:
        level = "关注"
    else:
        level = "警告"
    return score, level


def _ensure_utc(dt):
    """将 naive 或 aware datetime 统一转为 UTC aware"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def analyze_narrative_diff(user_id: str, db: Session, window_days: int = 7) -> Dict[str, Any]:
    """对比用户最近 window_days 天和之前 window_days 天的叙事文本

    返回 decline_score (0-100) 和四个维度的详细分析。
    数据不足时返回 decline_score=0、level="数据不足"。
    """
    now = datetime.now(timezone.utc)
    recent_start = now - timedelta(days=window_days)
    prev_start = recent_start - timedelta(days=window_days)

    sessions = db.query(DBSession).filter(
        DBSession.user_id == user_id,
        DBSession.narrative.isnot(None),
        DBSession.created_at >= prev_start,
    ).order_by(DBSession.created_at.asc()).all()

    recent_sessions = [s for s in sessions if _ensure_utc(s.created_at) >= recent_start]
    prev_sessions = [
        s for s in sessions
        if prev_start <= _ensure_utc(s.created_at) < recent_start
    ]

    # 数据不足时直接返回
    if len(recent_sessions) == 0 or len(prev_sessions) == 0:
        return {
            "decline_score": 0,
            "level": "数据不足",
            "window_days": window_days,
            "recent_session_count": len(recent_sessions),
            "previous_session_count": len(prev_sessions),
            "forgotten_entities": [],
            "narrative_simplification": {},
            "repetition": [],
            "anonymization_trend": {},
            "message": "近期或历史叙事数据不足，无法计算衰退分数",
        }

    recent_stats = _collect_session_stats(recent_sessions)
    prev_stats = _collect_session_stats(prev_sessions)

    forgotten = _detect_forgotten_entities(recent_stats, prev_stats, window_days)
    simplification = _detect_narrative_simplification(recent_stats, prev_stats)
    repetition = _detect_repetition(recent_stats, threshold=3)
    anon_trend = _detect_anonymization_trend(recent_stats, prev_stats)
    score, level = _compute_decline_score(forgotten, simplification, repetition, anon_trend)

    # 个人基线偏离检测：优先使用个人基线，若存在则增强或覆盖固定阈值
    personal_deviation = check_personal_deviation(
        user_id, recent_sessions[-1].metrics or {}, db
    ) if recent_sessions else {"deviated": False, "dimensions": []}

    explanation = None
    if personal_deviation.get("deviated"):
        explanation = get_baseline_explanation(personal_deviation)
        # 个人基线偏离时，若固定阈值未触发，则提升到至少"关注"
        danger_count = sum(
            1 for d in personal_deviation.get("dimensions", [])
            if d.get("severity") == "danger"
        )
        warning_count = sum(
            1 for d in personal_deviation.get("dimensions", [])
            if d.get("severity") == "warning"
        )
        if danger_count > 0 and level != "警告":
            level = "警告"
            score = max(score, 50)
        elif warning_count > 0 and level == "正常":
            level = "关注"
            score = max(score, 20)

    return {
        "decline_score": score,
        "level": level,
        "window_days": window_days,
        "recent_session_count": len(recent_sessions),
        "previous_session_count": len(prev_sessions),
        "forgotten_entities": forgotten,
        "narrative_simplification": simplification,
        "repetition": repetition,
        "anonymization_trend": anon_trend,
        "personal_deviation": personal_deviation,
        "explanation": explanation,
    }


def build_entity_timeline(user_id: str, db: Session, days: int = 30) -> Dict[str, Any]:
    """构建实体出现频率的时间线，标注哪些实体在消失

    返回：
      - timeline: [{ date, day_number, entities: {entity: count} }]
      - disappearing: [{ entity, last_seen_day, days_since_last_seen, peak_count }]
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    sessions = db.query(DBSession).filter(
        DBSession.user_id == user_id,
        DBSession.narrative.isnot(None),
        DBSession.created_at >= start,
    ).order_by(DBSession.created_at.asc()).all()

    timeline: List[Dict[str, Any]] = []
    entity_dates: Dict[str, List[str]] = defaultdict(list)
    entity_peak: Dict[str, int] = defaultdict(int)

    for s in sessions:
        text = s.narrative or ""
        ents = extract_entities(text)
        flat = _flatten_entities(ents)
        counts: Dict[str, int] = defaultdict(int)
        for e in flat:
            counts[e] += 1
            entity_dates[e].append(s.created_at.date().isoformat())
        for e, c in counts.items():
            if c > entity_peak[e]:
                entity_peak[e] = c
        timeline.append({
            "date": s.created_at.date().isoformat(),
            "day_number": s.day_number,
            "entities": dict(counts),
        })

    # 找出"消失中"的实体：最近 7 天未再出现，但历史至少出现过 2 次
    disappearing = []
    if sessions:
        last_date = sessions[-1].created_at.date()
        for ent, dates in entity_dates.items():
            if len(dates) < 2:
                continue
            last_seen = datetime.fromisoformat(dates[-1]).date()
            gap = (last_date - last_seen).days
            if gap >= 7:
                disappearing.append({
                    "entity": ent,
                    "last_seen": dates[-1],
                    "days_since_last_seen": gap,
                    "peak_count": entity_peak[ent],
                    "appearances": len(dates),
                })
    disappearing.sort(key=lambda x: x["days_since_last_seen"], reverse=True)

    return {
        "timeline": timeline,
        "disappearing": disappearing,
        "total_entities": len(entity_dates),
    }
