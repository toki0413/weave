# ============ 个人基线自适应预警服务 ============
"""基于用户自身历史会话构建个人基线，实现自适应偏离检测与预警。

核心功能：
1. build_personal_baseline — 从最近 N 条会话聚合指标均值/标准差
2. check_personal_deviation — 计算当前指标相对个人基线的 z-score 偏离
3. get_baseline_explanation — 将数值偏离转化为自然语言建议
"""

import json
import math
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models import Session as DBSession, Baseline

logger = logging.getLogger("cognitive_garden")

# 参与基线计算的指标键（与前端 metrics.js 对齐）
_BASELINE_KEYS = [
    "connectivity",
    "clustering",
    "centrality",
    "entropy",
    "density",
    "nodeCount",
    "edgeCount",
]

# 指标中文名与建议映射（用于自然语言解释）
_METRIC_META: Dict[str, Dict[str, str]] = {
    "connectivity": {
        "name": "人物节点关联度",
        "high_advice": "您的社交图谱关联度高于个人基线，社交网络活跃。",
        "low_advice": "人物节点关联度比您的个人基线低 {:.0f}%，建议关注社交活动，保持与亲友的联络。",
    },
    "clustering": {
        "name": "社交聚类系数",
        "high_advice": "社交聚类系数高于个人基线，社交圈子联系紧密。",
        "low_advice": "社交聚类系数比您的个人基线低 {:.0f}%，建议多参与群体活动，加强社交圈互动。",
    },
    "centrality": {
        "name": "自我中心度",
        "high_advice": "自我中心度高于个人基线，您在叙事中处于核心位置。",
        "low_advice": "自我中心度比您的个人基线低 {:.0f}%，建议多记录个人主动参与的活动。",
    },
    "entropy": {
        "name": "关系类型丰富度",
        "high_advice": "关系类型丰富度高于个人基线，叙事内容多样。",
        "low_advice": "关系类型丰富度比您的个人基线低 {:.0f}%，建议尝试不同类型的活动，丰富日常生活。",
    },
    "density": {
        "name": "图谱密度",
        "high_advice": "图谱密度高于个人基线，记忆网络连接紧密。",
        "low_advice": "图谱密度比您的个人基线低 {:.0f}%，建议多记录事件间的关联细节。",
    },
    "nodeCount": {
        "name": "实体节点数量",
        "high_advice": "实体节点数量高于个人基线，记忆内容丰富。",
        "low_advice": "实体节点数量比您的个人基线低 {:.0f}%，建议多记录生活中的人物、地点和事件。",
    },
    "edgeCount": {
        "name": "关系边数量",
        "high_advice": "关系边数量高于个人基线，记忆关联丰富。",
        "low_advice": "关系边数量比您的个人基线低 {:.0f}%，建议详细记录事件与人物、地点之间的关联。",
    },
}


def build_personal_baseline(
    user_id: str, db_session: Session, sample_size: int = 7
) -> Optional[Dict[str, Any]]:
    """为指定用户构建个人基线。

    从最近 ``sample_size`` 条会话中提取指标，计算均值与标准差，
    写入或更新 ``Baseline`` 表，并返回基线数据。

    Args:
        user_id: 用户 UUID。
        db_session: SQLAlchemy Session。
        sample_size: 参与计算的最近会话条数，默认 7。

    Returns:
        包含 ``personal_mean`` / ``personal_std`` / ``sample_count`` 的字典，
        或 ``None``（历史会话不足 2 条时无法计算标准差）。
    """
    sessions = (
        db_session.query(DBSession)
        .filter(
            DBSession.user_id == user_id,
            DBSession.metrics.isnot(None),
        )
        .order_by(DBSession.created_at.desc())
        .limit(sample_size)
        .all()
    )

    if len(sessions) < 2:
        logger.info(
            "用户 %s 历史会话不足 2 条，无法构建个人基线", user_id
        )
        return None

    # 收集指标序列
    series: Dict[str, List[float]] = {k: [] for k in _BASELINE_KEYS}
    for s in sessions:
        metrics = s.metrics or {}
        for k in _BASELINE_KEYS:
            val = metrics.get(k)
            if isinstance(val, (int, float)):
                series[k].append(float(val))

    # 计算均值与标准差（样本标准差，分母 n-1）
    personal_mean: Dict[str, float] = {}
    personal_std: Dict[str, float] = {}

    for k, vals in series.items():
        if len(vals) < 2:
            continue
        n = len(vals)
        mean = sum(vals) / n
        variance = sum((x - mean) ** 2 for x in vals) / (n - 1)
        std = math.sqrt(variance) if variance > 0 else 0.0
        personal_mean[k] = round(mean, 4)
        personal_std[k] = round(std, 4)

    # 写入 Baseline 表（upsert：一个用户只保留最新一条个人基线）
    baseline_row = (
        db_session.query(Baseline)
        .filter(
            Baseline.user_id == user_id,
            Baseline.session_id.is_(None),  # 个人基线不绑定具体 session
        )
        .first()
    )

    if baseline_row:
        baseline_row.personal_mean = personal_mean
        baseline_row.personal_std = personal_std
        baseline_row.sample_count = len(sessions)
        baseline_row.metrics = {
            "personal_mean": personal_mean,
            "personal_std": personal_std,
            "sample_count": len(sessions),
        }
        baseline_row.created_at = datetime.now(timezone.utc)
    else:
        baseline_row = Baseline(
            user_id=user_id,
            session_id=None,
            personal_mean=personal_mean,
            personal_std=personal_std,
            sample_count=len(sessions),
            metrics={
                "personal_mean": personal_mean,
                "personal_std": personal_std,
                "sample_count": len(sessions),
            },
        )
        db_session.add(baseline_row)

    db_session.commit()
    db_session.refresh(baseline_row)

    logger.info(
        "用户 %s 个人基线构建完成，样本 %d 条，指标 %d 个",
        user_id,
        len(sessions),
        len(personal_mean),
    )

    return {
        "personal_mean": personal_mean,
        "personal_std": personal_std,
        "sample_count": len(sessions),
    }


def check_personal_deviation(
    user_id: str, current_metrics: Dict[str, Any], db_session: Session
) -> Dict[str, Any]:
    """检测当前指标相对个人基线的偏离。

    对 ``personal_mean`` / ``personal_std`` 均存在的指标计算 z-score，
    任一指标 |z| > 2 时标记为偏离。返回结构化预警详情。

    Args:
        user_id: 用户 UUID。
        current_metrics: 当前会话的指标字典。
        db_session: SQLAlchemy Session。

    Returns:
        ``{"deviated": bool, "dimensions": [...]}`` 格式的字典。
    """
    baseline_row = (
        db_session.query(Baseline)
        .filter(
            Baseline.user_id == user_id,
            Baseline.session_id.is_(None),
        )
        .first()
    )

    if not baseline_row or not baseline_row.personal_mean or not baseline_row.personal_std:
        return {"deviated": False, "dimensions": []}

    mean_map: Dict[str, float] = baseline_row.personal_mean
    std_map: Dict[str, float] = baseline_row.personal_std

    dimensions: List[Dict[str, Any]] = []
    deviated = False

    for k in _BASELINE_KEYS:
        if k not in mean_map or k not in std_map:
            continue
        current = current_metrics.get(k)
        if not isinstance(current, (int, float)):
            continue

        mean = mean_map[k]
        std = std_map[k]
        if std == 0:
            # 标准差为 0 时无法计算 z-score，直接比较绝对差
            z_score = 0.0 if abs(current - mean) < 1e-6 else 999.0
        else:
            z_score = (current - mean) / std

        abs_z = abs(z_score)
        if abs_z > 2:
            deviated = True
            severity = "danger" if abs_z > 3 else "warning"
        else:
            severity = "normal"

        deviation_pct = (current - mean) / mean if mean != 0 else 0.0

        dimensions.append({
            "name": k,
            "current": round(float(current), 4),
            "baseline": round(mean, 4),
            "std": round(std, 4),
            "z_score": round(z_score, 4),
            "deviation_pct": round(deviation_pct, 4),
            "severity": severity,
        })

    # 按 |z_score| 降序排列
    dimensions.sort(key=lambda d: abs(d["z_score"]), reverse=True)

    return {"deviated": deviated, "dimensions": dimensions}


def get_baseline_explanation(deviation_result: Dict[str, Any]) -> Optional[str]:
    """将偏离检测结果转换为自然语言描述。

    选取偏离最严重（|z_score| 最大）的维度，生成一条用户可读的说明。
    如果未偏离，返回 ``None``。

    Args:
        deviation_result: ``check_personal_deviation`` 的返回值。

    Returns:
        自然语言字符串，或 ``None``（无偏离时）。
    """
    if not deviation_result.get("deviated"):
        return None

    dims = deviation_result.get("dimensions", [])
    if not dims:
        return None

    # 只取 severity != normal 的维度，再按 |z_score| 排序
    alert_dims = [d for d in dims if d["severity"] != "normal"]
    if not alert_dims:
        return None

    alert_dims.sort(key=lambda d: abs(d["z_score"]), reverse=True)
    top = alert_dims[0]
    meta = _METRIC_META.get(top["name"], {})
    name = meta.get("name", top["name"])
    pct = abs(top["deviation_pct"]) * 100

    if top["deviation_pct"] < 0:
        advice = meta.get("low_advice", f"{name} 比您的个人基线低 {pct:.0f}%，建议关注。")
        advice = advice.format(pct)
    else:
        advice = meta.get("high_advice", f"{name} 高于您的个人基线 {pct:.0f}%，表现良好。")
        # high_advice 不含占位符，直接返回；如果含占位符则格式化
        if "{" in advice:
            advice = advice.format(pct)

    return advice
