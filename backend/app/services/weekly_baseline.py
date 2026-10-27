# ============ 周粒度个人基线 ============
"""把会话按 ISO 周（本地 +480）聚合成周指标，再对"最近一周 vs 之前 N 周"
做 z 偏离分层。tier_engine 只认 (Signal, BaselineStats)，本模块负责从
DB 会话里把它喂出来。

三个刻意决定（详见 docs/周基线-数据来源边界与测试点.md，此处只留结论）：

1) 图谱 7 键（connectivity/clustering/.../nodeCount/edgeCount）**不进基线**。
   它们全部由"截至该会话时刻的完整图谱"算出（graph/metrics.js:4-6 直接读
   state.nodes/edges，而图谱跨会话累积），对单调增长量取 12 周均值当基线，
   偏离检验会把"图谱停止生长"与"认知衰退"混为一谈。改用周内增量
   node_delta / edge_delta / anon_delta（周内 max−min，恒有定义）。

2) 会话级即时反馈（check_personal_deviation 对单条会话算 z）存在量纲错配：
   一周 3–7 条的均值波动约是单条的 1/√k，z 被系统性放大。在周基线成熟前，
   analyze_narrative_diff 里的 legacy 分数封顶在"关注"，不出"警告"。

3) 有效周谓词全站唯一：low_confidence is not True 且叙事可解密且非空，
   且该周可计数会话 ≥ min_sessions_per_week。周表（pilot_export）与基线
   必须同源，否则周表报"有效周 12"、基线 n=9，试点报告自相矛盾。

基线**不落库**，按请求现算：试点规模（3–5 人 × ~100 会话）下解密全量叙事
是秒级；等真的需要历史轨迹再引入存储，避免一次迁移背两个决定。
"""
import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models import Session as DBSession
from app.services.decline import (
    _collect_session_stats,
    _detect_repetition,
    _ensure_utc,
)
from app.services.narrative_text import decrypt_narrative, DECRYPT_FAILED
from app.services.pilot_export import _local as to_local
from app.services.tier_engine import (
    Direction,
    Signal,
    TierConfig,
    TierResult,
    evaluate_tier,
    next_step,
)

logger = logging.getLogger("cognitive_garden")

DEFAULT_TZ_OFFSET_MINUTES = 8 * 60
MIN_SESSIONS_PER_WEEK = 3          # 有效周门槛，与 pilot_export 同源语义
# 13 = 12 个基线周 + 1 个"当前信号周"。evaluate_user_tier 取最后一周做当前信号、
# 前 12 周做基线：如果这里只留 12，减掉当前周后基线只剩 11 < min_usable_samples。
WINDOW_WEEKS = 13
CURRENT_WEEK_FOR_TIER = 1          # 最近 1 周作为"当前信号"，其余进基线

# 指标方向注册表。新增指标必须同时在这里登记方向，
# 未登记的指标 tier_engine 会按 HIGH_IS_GOOD 处理（默认值），那是静默错误。
SIGNAL_DIRECTIONS: Dict[str, Direction] = {
    # 叙事侧（decline._collect_session_stats 产出，会话级、非累积）
    "entity_density":   Direction.HIGH_IS_GOOD,
    "avg_sentence_len": Direction.HIGH_IS_GOOD,
    "anon_ratio":       Direction.HIGH_IS_BAD,
    "avg_filler_rate":  Direction.HIGH_IS_BAD,
    "repetition_events": Direction.HIGH_IS_BAD,
    # 音频侧（stt._extract_audio_features，会话级、非累积）
    "audio_duration_sec":     Direction.HIGH_IS_GOOD,
    "audio_speech_ratio":     Direction.HIGH_IS_GOOD,
    "audio_pause_count":      Direction.HIGH_IS_BAD,
    "audio_words_per_minute": Direction.HIGH_IS_GOOD,
    # 图谱增量（本模块计算，替代退出基线的 7 个快照键）
    "node_delta": Direction.HIGH_IS_GOOD,
    "edge_delta": Direction.HIGH_IS_GOOD,
    "anon_delta": Direction.HIGH_IS_BAD,
}

# 指标缺失（如存量会话没有 metrics.audio）时按"未采集"处理：
# 不参与该指标的均值/标准差，也不计为 0 拉低均值 —— 与 low_confidence=NULL
# 的"未知不等于不可信"同一原则。
_AUDIO_KEYS = ["duration_sec", "speech_ratio", "pause_count", "words_per_minute"]


def _week_start(dt_local: date) -> date:
    """ISO 周一。跨年周用 isocalendar 的年份，不能用 date.year。"""
    return dt_local - timedelta(days=dt_local.weekday())


def _usable(sessions: List[DBSession], user_id: str) -> List[DBSession]:
    """有效会话：低置信剔除 + 解密失败剔除 + 空叙事剔除。

    谓词与 baseline_personal._countable、pilot_export 的口径一致；
    三处必须同步改，本文件 docstring 顶部有记。
    """
    out = []
    for s in sessions:
        if s.low_confidence is True:
            continue
        nt = decrypt_narrative(s.narrative, user_id, bool(s.is_encrypted))
        if nt.state == DECRYPT_FAILED or not nt.text.strip():
            continue
        out.append(s)
    return out


def _week_metrics(week_sessions: List[DBSession], user_id: str) -> Optional[Dict[str, Any]]:
    """单个有效周的指标向量。样本不足返回 None。"""
    stats = _collect_session_stats(week_sessions, user_id)
    repetition = _detect_repetition(stats, threshold=3)

    # 图谱周内增量：max−min 对累积量恒有定义，单会话周为 0
    def _delta(key):
        vals = [(s.metrics or {}).get(key) for s in week_sessions]
        vals = [v for v in vals if isinstance(v, (int, float))]
        return (max(vals) - min(vals)) if vals else None

    audio_vals: Dict[str, List[float]] = defaultdict(list)
    audio_unknown = 0
    for s in week_sessions:
        audio = (s.metrics or {}).get("audio") or {}
        got = False
        for k in _AUDIO_KEYS:
            v = audio.get(k)
            if isinstance(v, (int, float)):
                audio_vals[k].append(float(v))
                got = True
        if not got:
            audio_unknown += 1

    def _mean(key):
        vals = audio_vals.get(key)
        return (sum(vals) / len(vals)) if vals else None

    m: Dict[str, Any] = {
        "entity_density": stats["avg_entity_density"],
        "avg_sentence_len": stats["avg_sentence_len"],
        "anon_ratio": stats["anon_ratio"],
        "avg_filler_rate": stats["avg_filler_rate"],
        "repetition_events": float(len(repetition)),
        "node_delta": _delta("nodeCount"),
        "edge_delta": _delta("edgeCount"),
        "anon_delta": _delta("anonCount"),
        "audio_duration_sec": _mean("duration_sec"),
        "audio_speech_ratio": _mean("speech_ratio"),
        "audio_pause_count": _mean("pause_count"),
        "audio_words_per_minute": _mean("words_per_minute"),
    }
    m = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()}
    return {
        "metrics": m,
        "session_count": len(week_sessions),
        "audio_unknown": audio_unknown,
    }


def build_weekly_baseline(db: Session, user_id: str,
                          min_sessions_per_week: int = MIN_SESSIONS_PER_WEEK,
                          window_weeks: int = WINDOW_WEEKS,
                          tz_offset_minutes: int = DEFAULT_TZ_OFFSET_MINUTES
                          ) -> Dict[str, Any]:
    """按周聚合 → 有效周列表。不落库，按请求现算。

    返回 {"weeks": [...], "excluded_low_confidence": int, "decrypt_failed": int}
    weeks 按时间升序，每周 {"week_start", "iso_week", "metrics", "session_count"}。
    不足 min_sessions_per_week 的周直接跳过、不计入 n。
    """
    sessions = (db.query(DBSession)
                  .filter(DBSession.user_id == user_id)
                  .filter(DBSession.narrative.isnot(None))
                  .order_by(DBSession.created_at.asc())
                  .all())

    buckets: Dict[date, List[DBSession]] = defaultdict(list)
    excluded_low_conf = 0
    decrypt_failed = 0
    for s in sessions:
        if s.low_confidence is True:
            excluded_low_conf += 1
            continue
        if s.narrative is None:
            continue
        nt = decrypt_narrative(s.narrative, user_id, bool(s.is_encrypted))
        if nt.state == DECRYPT_FAILED:
            decrypt_failed += 1
            continue
        local = to_local(_ensure_utc(s.created_at), tz_offset_minutes)
        if local is None:
            continue
        buckets[_week_start(local.date())].append(s)

    weeks: List[Dict[str, Any]] = []
    for ws in sorted(buckets):
        usable = _usable(buckets[ws], user_id)
        if len(usable) < min_sessions_per_week:
            continue                      # 不建值，也不计入 n
        wm = _week_metrics(usable, user_id)
        if wm is None:
            continue
        y, w, _ = ws.isocalendar()
        weeks.append({
            "week_start": ws.isoformat(),
            "iso_week": f"{y}-W{w:02d}",
            **wm,
        })

    weeks = weeks[-window_weeks:]
    return {
        "weeks": weeks,
        "excluded_low_confidence": excluded_low_conf,
        "decrypt_failed": decrypt_failed,
    }


def _mean_std(vals: List[float]) -> Dict[str, float]:
    n = len(vals)
    mean = sum(vals) / n
    if n < 2:
        return {"mean": mean, "std": 0.0, "n": n}
    var = sum((x - mean) ** 2 for x in vals) / (n - 1)
    return {"mean": mean, "std": var ** 0.5, "n": n}


def evaluate_user_tier(db: Session, user_id: str,
                       cfg: Optional[TierConfig] = None) -> Dict[str, Any]:
    """最近一周的信号 vs 之前有效周的基线 → tier 结果。

    基线**不含当前周**：把被评估的那一周算进基线会向均值回归、稀释信号。
    n（有效周）不足 cfg.min_usable_samples（默认 12，源于
    max_attainable_z=(n-1)/√n 需 ≥ danger_z）时返回 insufficient_data，
    附 n 与可达上界，绝不猜档。
    """
    cfg = cfg or TierConfig()
    built = build_weekly_baseline(db, user_id)
    weeks = built["weeks"]

    out: Dict[str, Any] = {
        "config_version": "tier-v0.1-uncalibrated",
        "baseline_weeks": max(0, len(weeks) - 1),
        "valid_weeks": len(weeks),
        "excluded_low_confidence": built["excluded_low_confidence"],
        "decrypt_failed": built["decrypt_failed"],
    }

    if len(weeks) < 2:
        out.update({"tier": "insufficient_data",
                    "tier_reason": "有效周不足，无法区分当前周与基线",
                    "max_attainable_z": None})
        return out

    current = weeks[-1]["metrics"]
    baseline_weeks = [w["metrics"] for w in weeks[:-1]]
    n_base = len(baseline_weeks)

    from app.services.tier_engine import max_attainable_z as _maz
    attainable = _maz(n_base)

    if n_base < cfg.min_usable_samples:
        out.update({"tier": "insufficient_data",
                    "tier_reason": f"基线仅 {n_base} 个有效周，"
                                   f"danger_z={cfg.danger_z} 结构上不可达",
                    "max_attainable_z": round(attainable, 3)})
        return out

    signals: List[Signal] = []
    baselines: Dict[str, Any] = {}
    for name, direction in SIGNAL_DIRECTIONS.items():
        cur = current.get(name)
        hist = [w[name] for w in baseline_weeks if isinstance(w.get(name), (int, float))]
        signals.append(Signal(name=name, value=cur, direction=direction))
        if hist:
            st = _mean_std(hist)
            baselines[name] = {"mean": st["mean"], "std": st["std"] or None, "n": st["n"]}
        else:
            baselines[name] = {"mean": None, "std": None, "n": 0}

    from app.services.tier_engine import BaselineStats
    stats = {k: BaselineStats(mean=v["mean"], std=v["std"], n=v["n"])
             for k, v in baselines.items() if v["mean"] is not None}

    result: TierResult = evaluate_tier(signals, stats, cfg,
                                       config_version=out["config_version"])
    d = result.to_dict()
    out.update({
        "tier": d["tier"],
        "level": d["level"],
        "decline_score": d["decline_score"],
        "tier_counts": d["counts"],
        "tier_signals": d["signals"],
        "tier_reason": d["reason"] or result.reason,
        "max_attainable_z": round(_maz(n_base), 3),
        "next_step": next_step(result),
    })
    return out
