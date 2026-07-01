# ============ HEALTH COMPUTATION (Backend mirror of frontend) ============
from typing import List, Dict, Any, Optional

def compute_structural_score(m: Dict[str, Any]) -> float:
    return m.get("connectivity", 0) * 0.35 + m.get("clustering", 0) * 0.35 + m.get("globalEff", 0) * 0.30

def compute_contentual_score(m: Dict[str, Any], anomalies: List[Dict], anon_ratio: float) -> float:
    anomaly_penalty = 0.85 ** len(anomalies)
    anon_penalty = max(0, 1 - anon_ratio * 3)
    type_counts = m.get("typeCounts", {})
    coverage = min(1, len(type_counts) / 4) if m.get("edgeCount", 0) > 0 else 0
    return anomaly_penalty * anon_penalty * (0.6 + 0.4 * coverage)

def compute_trend_score(current: Dict[str, Any], baseline: Optional[Dict[str, Any]], history: List[float]) -> float:
    if not baseline:
        return 1.0
    drift = abs(current.get("connectivity", 0) - baseline.get("connectivity", 0)) + \
            abs(current.get("clustering", 0) - baseline.get("clustering", 0)) + \
            abs(current.get("globalEff", 0) - baseline.get("globalEff", 0))
    import math
    drift_score = math.exp(-drift * 3)
    if len(history) >= 3:
        last3 = history[-3:]
        declining = last3[0] > last3[1] > last3[2]
        if declining:
            return drift_score * 0.7
    return drift_score

def compute_health(
    m: Dict[str, Any],
    anomalies: List[Dict],
    baseline: Optional[Dict[str, Any]] = None,
    history: List[float] = [],
    personal_baseline: Optional[Dict[str, Any]] = None,
) -> int:
    """计算综合健康分。

    Args:
        m: 当前指标字典。
        anomalies: 异常列表。
        baseline: 群体/固定基线（用于趋势漂移）。
        history: 历史健康分列表。
        personal_baseline: 个人基线数据，若提供则基于偏离程度额外惩罚。

    Returns:
        0-100 的整数健康分。
    """
    if not m:
        return 0
    anon_ratio = m.get("anonCount", 0) / m.get("nodeCount", 1) if m.get("nodeCount", 0) > 0 else 0
    s = compute_structural_score(m)
    c = compute_contentual_score(m, anomalies, anon_ratio)
    t = compute_trend_score(m, baseline, history)
    score = 100 * s * c * t

    # 个人基线偏离惩罚：偏离越大，惩罚越重
    if personal_baseline and personal_baseline.get("personal_mean"):
        import math

        mean_map = personal_baseline["personal_mean"]
        std_map = personal_baseline.get("personal_std", {})
        keys = ["connectivity", "clustering", "centrality", "entropy", "density"]
        total_z = 0.0
        count = 0
        for k in keys:
            if k not in mean_map or k not in m:
                continue
            mean = mean_map[k]
            std = std_map.get(k, 0) if std_map else 0
            if std and std > 0:
                z = abs((m[k] - mean) / std)
            else:
                z = abs(m[k] - mean)
            total_z += z
            count += 1
        avg_z = total_z / count if count > 0 else 0.0
        # 指数衰减：avg_z = 0 → penalty = 1.0；avg_z = 2 → penalty ≈ 0.37
        penalty = math.exp(-avg_z * 0.5)
        score *= penalty

    return round(max(0, min(100, score)))
