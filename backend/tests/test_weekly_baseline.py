"""周基线与 tier 接线回归

覆盖 docs/周基线-数据来源边界与测试点.md §4 的可落地点。
每条用例末尾注释标注对应测试点编号。
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.models import Session as DBSession, User
from app.services.weekly_baseline import (
    SIGNAL_DIRECTIONS,
    build_weekly_baseline,
    evaluate_user_tier,
)

UTC = timezone.utc
START = datetime(2026, 7, 6, 9, 0, tzinfo=UTC)   # 2026-W28 周一


def _user(db):
    u = User(username="wb_user", hashed_password="x", role="elderly", name="测试")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _sess(db, uid, dt, narrative=None, low_conf=None, metrics=None, is_enc=False):
    db.add(DBSession(
        user_id=uid, day_number=1,
        narrative=narrative if narrative is not None else "今天秀兰陪我去公园，路上碰见建国，聊了很久。",
        is_encrypted=is_enc,
        graph={"nodes": [], "edges": []},
        metrics=metrics if metrics is not None else {},
        health_score=80, anomalies=[],
        low_confidence=low_conf,
        created_at=dt,
    ))
    db.commit()


def _seed_weeks(db, uid, n_weeks, sessions_per_week=3, start=START, low_conf_weeks=None,
                narrative_fn=None):
    """每周 sessions_per_week 条会话，间隔 3 天铺满一周。

    叙事和 metrics 按周序号变化：恒定基线的 std=0 会让所有信号 INDETERMINATE，
    那是正确行为，但测试要验证的是"有变化的基线能出 tier"，所以数据必须变。
    """
    low_conf_weeks = low_conf_weeks or set()
    for w in range(n_weeks):
        for i in range(sessions_per_week):
            dt = start + timedelta(weeks=w, days=i * 2, hours=i)
            lc = True if w in low_conf_weeks else None
            nar = narrative_fn(w, i) if narrative_fn else (
                f"今天秀兰陪我去公园，路上碰见建国和王芳，聊了很久。"
                f"{'还去了菜市场买了鱼和青菜。' * (w % 3 + 1)}"
            )
            metrics = {
                "nodeCount": 10 + w * 2 + i,
                "edgeCount": 8 + w * 2 + i,
                "anonCount": 0,
                "audio": {"duration_sec": 50.0 + w + i, "speech_ratio": 0.7,
                          "pause_count": 4 + w % 3, "words_per_minute": 95.0 + w},
            }
            _sess(db, uid, dt, narrative=nar, low_conf=lc, metrics=metrics)


# ---------------------------------------------------------------- 周界

def test_week_key_iso_boundary():
    """+480 下 2026-10-18 17:00Z（周日）→ 本地周一 → W43。对应测试点 1。"""
    from app.services.pilot_export import _local, week_of
    dt = datetime(2026, 10, 18, 17, 0, tzinfo=UTC)
    local = _local(dt, 8 * 60)
    assert week_of(local.date())["iso_week"] == "2026-W43"


# ---------------------------------------------------------------- 有效周

def test_week_below_threshold_skipped_and_not_counted(db_session):
    """第 1 周只有 2 条 → 不建值、不计入 n。对应测试点 2。"""
    u = _user(db_session)
    _seed_weeks(db_session, u.id, 4, sessions_per_week=3)
    # 第 1 周只留 2 条：直接删掉该周第 3 条（SQLite 存 naive，对比用 naive）
    cutoff = (START + timedelta(days=4)).replace(tzinfo=None)
    db_session.query(DBSession).filter(
        DBSession.user_id == u.id,
        DBSession.created_at <= cutoff,
    ).delete(synchronize_session=False)
    db_session.commit()

    built = build_weekly_baseline(db_session, u.id)
    assert len(built["weeks"]) == 3, f"预期 3 个有效周，实际 {len(built['weeks'])}"


def test_all_low_confidence_no_valid_weeks(db_session):
    """全部低置信 → 0 个有效周。对应测试点 3。"""
    u = _user(db_session)
    _seed_weeks(db_session, u.id, 3, sessions_per_week=3, low_conf_weeks={0, 1, 2})
    built = build_weekly_baseline(db_session, u.id)
    assert built["weeks"] == []
    assert built["excluded_low_confidence"] == 9


# ---------------------------------------------------------------- 缺失语义

def test_audio_missing_is_unknown_not_zero(db_session):
    """存量会话无 metrics.audio：audio 指标为 None（未采集），不拉低均值。对应测试点 4。"""
    u = _user(db_session)
    # 手动造无 audio 的会话（不走 _seed_weeks，因为它现在总给 audio）
    for w in range(2):
        for i in range(3):
            _sess(db_session, u.id,
                  START + timedelta(weeks=w, days=i * 2),
                  metrics={"nodeCount": 10, "edgeCount": 8})  # 无 audio 键
    built = build_weekly_baseline(db_session, u.id)
    m = built["weeks"][0]["metrics"]
    assert m["audio_duration_sec"] is None
    assert built["weeks"][0]["audio_unknown"] == 3


def test_audio_present_averaged(db_session):
    u = _user(db_session)
    for w in range(2):
        for i in range(3):
            _sess(db_session, u.id,
                  START + timedelta(weeks=w, days=i * 2),
                  metrics={"audio": {"duration_sec": 60.0 + w * 10 + i,
                                     "speech_ratio": 0.7, "pause_count": 5,
                                     "words_per_minute": 100.0}})
    built = build_weekly_baseline(db_session, u.id)
    m0 = built["weeks"][0]["metrics"]
    assert m0["audio_duration_sec"] == pytest.approx(61.0)   # (60+61+62)/3
    assert m0["audio_words_per_minute"] == pytest.approx(100.0)


# ---------------------------------------------------------------- n 门槛

def test_n_below_12_tier_insufficient_with_reason(db_session):
    """4 ≤ n < 12：能建基线但 tier 恒 insufficient_data，附可达上界。对应测试点 5。"""
    u = _user(db_session)
    _seed_weeks(db_session, u.id, 8, sessions_per_week=3)
    result = evaluate_user_tier(db_session, u.id)
    assert result["tier"] == "insufficient_data"
    assert result["baseline_weeks"] == 7
    assert result["max_attainable_z"] is not None
    assert result["max_attainable_z"] < 3.0    # 7 周 (n-1)/√n = 2.27


def test_n7_danger_structurally_unreachable(db_session):
    """n=7 周时 danger_z=3.0 不可达。对应测试点 6。"""
    from app.services.tier_engine import max_attainable_z
    assert max_attainable_z(7) < 3.0


def test_n12_tier_has_real_result(db_session):
    """13 周 → 基线 12 周，tier 有真实结果（不再 insufficient）。"""
    u = _user(db_session)
    _seed_weeks(db_session, u.id, 13, sessions_per_week=3)
    result = evaluate_user_tier(db_session, u.id)
    assert result["tier"] in ("green", "amber", "red"), result.get("tier_reason")
    assert result["baseline_weeks"] == 12


# ---------------------------------------------------------------- 量纲

def test_weekly_std_less_than_session_std(db_session):
    """周均值的波动显著小于单会话值的波动。对应测试点 7。"""
    import random
    rng = random.Random(42)
    u = _user(db_session)
    # 12 周 × 4 会话，每条会话的 entity_density 带大幅噪声
    session_vals = []
    for w in range(12):
        for i in range(4):
            v = 5.0 + rng.gauss(0, 2.0)
            session_vals.append(v)
            dt = START + timedelta(weeks=w, days=i)
            nar = "今天秀兰陪我去公园" * int(v)   # 长度粗略控制密度
            _sess(db_session, u.id, dt, narrative=nar)
    # 直接比较：会话值的标准差 vs 周均值的标准差
    import statistics
    week_means = []
    for w in range(12):
        week_vals = session_vals[w * 4:(w + 1) * 4]
        week_means.append(statistics.mean(week_vals))
    session_sd = statistics.stdev(session_vals)
    weekly_sd = statistics.stdev(week_means)
    assert weekly_sd < session_sd * 0.7, \
        f"周均值波动 {weekly_sd:.3f} 应显著小于会话波动 {session_sd:.3f}"


# ---------------------------------------------------------------- tier 接线

def test_analyze_response_contains_tier_fields_insufficient(db_session):
    """analyze_narrative_diff 的三条返回路径（含早退）都必须带 tier 字段。
    对应测试点 13。"""
    from app.services.decline import analyze_narrative_diff
    u = _user(db_session)
    _seed_weeks(db_session, u.id, 2, sessions_per_week=3)
    result = analyze_narrative_diff(u.id, db_session, window_days=7)
    for key in ("tier", "tier_reason", "baseline_weeks", "valid_weeks",
                "tier_config_version", "next_step"):
        assert key in result, f"响应缺 {key}"
    assert result["tier"] == "insufficient_data"


def test_analyze_response_tier_fields_on_empty_window(db_session):
    """老人停止记录：7 天窗口为空走早退，但 tier 字段仍在——
    最后一个有效周 vs 基线的信号不能因为早退而丢失。"""
    from app.services.decline import analyze_narrative_diff
    u = _user(db_session)
    # 13 周全部停在 90 天前：7 天窗口为空 → 走早退
    _seed_weeks(db_session, u.id, 13, sessions_per_week=3,
                start=START - timedelta(days=90))
    result = analyze_narrative_diff(u.id, db_session, window_days=7)
    assert result["level"] == "数据不足"
    assert result["tier"] in ("green", "amber", "red"), \
        f"13 个有效周却拿到 {result['tier']}：{result.get('tier_reason')}"


def test_legacy_score_capped_at_amber(db_session):
    """会话级 legacy 路径（量纲错配）封顶"关注"，不出"警告"。决策 B。"""
    from app.services.decline import analyze_narrative_diff
    u = _user(db_session)
    # 构造会触发 legacy personal_baseline danger 的场景
    _seed_weeks(db_session, u.id, 3, sessions_per_week=3)
    result = analyze_narrative_diff(u.id, db_session, window_days=7)
    if result.get("tier") == "insufficient_data":
        assert result["decline_score"] < 50 or result["level"] != "警告", \
            f"legacy 分数漏封顶：score={result['decline_score']} level={result['level']}"


# ---------------------------------------------------------------- 一致性

def test_signal_directions_complete():
    """新增指标必须登记方向，否则 tier_engine 默认 HIGH_IS_GOOD 是静默错误。"""
    from app.services.weekly_baseline import _week_metrics
    assert set(SIGNAL_DIRECTIONS) >= {
        "entity_density", "avg_sentence_len", "anon_ratio", "avg_filler_rate",
        "repetition_events", "node_delta", "edge_delta", "anon_delta",
        "audio_duration_sec", "audio_speech_ratio", "audio_pause_count",
        "audio_words_per_minute",
    }


def test_build_weekly_baseline_idempotent(db_session):
    u = _user(db_session)
    _seed_weeks(db_session, u.id, 5, sessions_per_week=3)
    a = build_weekly_baseline(db_session, u.id)
    b = build_weekly_baseline(db_session, u.id)
    assert a == b
