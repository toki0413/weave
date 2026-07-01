"""健康度计算测试"""
from app.services.health import compute_health


def _perfect_metrics():
    """接近满分的指标：结构满分、无匿名、单关系类型"""
    return {
        "connectivity": 1.0,
        "clustering": 1.0,
        "globalEff": 1.0,
        "nodeCount": 3,
        "edgeCount": 3,
        "anonCount": 0,
        "typeCounts": {"friend": 3},
    }


def test_empty_metrics_returns_0():
    """空指标应返回 0"""
    assert compute_health({}, [], None, []) == 0


def test_perfect_graph_high_score():
    """完美图谱应拿到较高分数（结构满分 + 单类型覆盖）"""
    m = _perfect_metrics()
    score = compute_health(m, [], None, [])
    # 结构 s=1.0，覆盖 coverage=0.25，c=0.6+0.4*0.25=0.7，t=1.0
    # 100 * 1.0 * 0.7 * 1.0 = 70
    assert score >= 60


def test_anomaly_penalty():
    """有异常时分数应低于无异常"""
    m = _perfect_metrics()
    without = compute_health(m, [], None, [])
    with_anom = compute_health(
        m, [{"event": "吃药", "severity": "warn"}], None, []
    )
    assert with_anom < without


def test_anon_penalty():
    """匿名节点比例越高分数越低"""
    m = _perfect_metrics()
    clean = compute_health(m, [], None, [])

    m_with_anon = dict(m)
    m_with_anon["anonCount"] = 1
    m_with_anon["nodeCount"] = 4
    penalized = compute_health(m_with_anon, [], None, [])
    assert penalized < clean


def test_trend_decline():
    """连续下降趋势应额外惩罚"""
    m = _perfect_metrics()
    baseline = {
        "connectivity": 1.0,
        "clustering": 1.0,
        "globalEff": 1.0,
    }
    # 当前指标与基线一致，drift=0，drift_score=1
    declining = [90, 80, 70]   # 持续下降
    rising = [70, 80, 90]      # 持续上升
    score_decline = compute_health(m, [], baseline, declining)
    score_rising = compute_health(m, [], baseline, rising)
    assert score_decline < score_rising


def test_no_baseline_no_penalty():
    """没有基线时趋势分应为 1，不额外扣分"""
    m = _perfect_metrics()
    score = compute_health(m, [], None, [])
    # 和有基线但无下降趋势、drift=0 的情况应一致
    baseline = {
        "connectivity": 1.0,
        "clustering": 1.0,
        "globalEff": 1.0,
    }
    score_with_baseline = compute_health(m, [], baseline, [])
    assert score == score_with_baseline
