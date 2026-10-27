# ============ 三色分层引擎（语言无关 / 无 DB / 纯函数）===========
"""tier_engine —— 把"多维 z 偏离"折叠成绿/琥珀/红分层的唯一权威实现。

设计约束（改动本文件前先读）：
1. 纯函数，不 import sqlalchemy、不读 config、不查库。这样它可以在
   DementiaBank / ADReSSo / CCC 的任何特征序列上直接复用，也便于单测。
2. 只吃 ``Signal(name, value)`` + ``BaselineStats``；方向（direction）由调用方
   注册表提供，本文件不硬编码任何指标语义。指标语义属于 decline_features 层。
3. **阈值不是临床常数**。``TierConfig`` 里的默认值是结构可调参数，
   供后续用标定数据（外部语料横断面 + 试点纵向）优化，
   不得在未标定时对外宣称具有临床效力。
4. 样本/基线不足时返回 INSUFFICIENT_DATA，**不猜一个分**。这是本模块存在的
   主要理由：替代旧实现里"没基线也给 0 分/给 999 z"的两处硬伤。

旧标度对照（用于兼容前端）：
    正常 → green    关注 → amber    警告 → red    数据不足 → insufficient_data
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence

# ---------------------------------------------------------------- 枚举


class Tier(str, Enum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"
    INSUFFICIENT_DATA = "insufficient_data"

    @property
    def legacy_level(self) -> str:
        """兼容旧 ``level`` 中文字段，前端未改造前按此映射。"""
        return {
            Tier.GREEN: "正常",
            Tier.AMBER: "关注",
            Tier.RED: "警告",
            Tier.INSUFFICIENT_DATA: "数据不足",
        }[self]


class Direction(str, Enum):
    """该指标"往哪个方向走算风险"。"""

    HIGH_IS_GOOD = "high_is_good"   # 越高越好（实体密度、连通度）→ 负向偏离才是风险
    HIGH_IS_BAD = "high_is_bad"     # 越高越差（匿名化比例、填充词率）→ 正向偏离才是风险
    TWO_SIDED = "two_sided"         # 双向都算异常（罕见，需显式声明）


class Severity(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"
    DANGER = "danger"
    INDETERMINATE = "indeterminate"   # 无法计算，**不参与计票**


# 旧代码里 severity 用裸字符串；统一走这里，避免拼写漂移
_LEGACY_SEVERITY = {
    "normal": Severity.NORMAL,
    "warning": Severity.WARNING,
    "danger": Severity.DANGER,
    "indeterminate": Severity.INDETERMINATE,
}


# ---------------------------------------------------------------- 数据结构


@dataclass(frozen=True)
class Signal:
    """一个待评估指标。value=None 表示该样本没算出这个特征。"""

    name: str
    value: Optional[float]
    direction: Direction = Direction.HIGH_IS_GOOD


@dataclass(frozen=True)
class BaselineStats:
    """个人基线的均值/标准差。n 为参与该基线的样本条数（可为 None）。"""

    mean: float
    std: Optional[float]
    n: Optional[int] = None


@dataclass(frozen=True)
class TierConfig:
    warning_z: float = 2.0
    danger_z: float = 3.0

    # 基线构建门槛（属 baseline 层语义，engine 只在显式传入 n 时校验）
    min_baseline_samples: int = 4

    # 出档门槛：可计票的基线周数 < 此值一律 INSUFFICIENT_DATA。
    # ⚠ 数学依据：样本量为 n 时，单点可达的最大 z = (n-1)/sqrt(n)：
    #     n=4 → 1.500   n=7 → 2.268   n=10 → 2.846   n=12 → 3.175
    #   故 danger_z=3.0 在 n<12 时**结构上不可达**，红档会退化成永不触发的死代码
    #   （旧实现里唯一能造出 danger 的，是 std==0 填 999.0 的那个哨兵值）。
    #   取 12 为下限，同时给 std 留最低可靠自由度。
    min_usable_samples: int = 12

    # 出档所需的最少信号维度数（单维不足以定档）
    min_usable_signals: int = 3

    # 红必须有第二个 danger 维度佐证；单个 danger 一律封顶在琥珀。
    # 有意保守：漏报可由下次复评补上，误报会直接消耗家属信任
    # （Notification.resolution_status=false_alarm 闭环已证明误报会被回填）。
    red_requires_corroboration: bool = True


def max_attainable_z(n: int) -> float:
    """样本量 n 时单点可达的最大 |z|（样本标准差，分母 n-1）。

    用于判断某组阈值在当前基线样本量下**是否可能被触发**，
    防止把"从未触发"误读成"用户状态良好"。
    """
    if n < 2:
        return 0.0
    return (n - 1) / math.sqrt(n)


@dataclass(frozen=True)
class SignalAssessment:
    name: str
    value: Optional[float]
    direction: Direction
    mean: Optional[float]
    std: Optional[float]
    z_score: Optional[float]
    risk_z: Optional[float]
    severity: Severity
    reason: str = ""
    n: Optional[int] = None          # 该基线的样本数（周数），用于可达性门槛

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "value": self.value,
            "direction": self.direction.value,
            "mean": self.mean,
            "std": self.std,
            "z_score": self.z_score,
            "risk_z": self.risk_z,
            "severity": self.severity.value,
            "baseline_n": self.n,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class TierResult:
    tier: Tier
    config_version: str
    signals: List[SignalAssessment]
    usable_count: int
    danger_count: int
    warning_count: int
    indeterminate_count: int
    reason: str

    @property
    def decline_score(self) -> int:
        """兼容旧 ``decline_score`` 的确定性单调映射，**不是**独立算法。

        新代码一律读 ``tier``；此字段仅为过渡期前端与历史快照保留。
        """
        return {
            Tier.GREEN: 0,
            Tier.AMBER: 30,
            Tier.RED: 60,
            Tier.INSUFFICIENT_DATA: 0,
        }[self.tier]

    @property
    def level(self) -> str:
        """兼容旧 ``level`` 中文字段。"""
        return self.tier.legacy_level

    def to_dict(self) -> Dict[str, object]:
        return {
            "tier": self.tier.value,
            "level": self.level,
            "decline_score": self.decline_score,
            "config_version": self.config_version,
            "counts": {
                "usable": self.usable_count,
                "danger": self.danger_count,
                "warning": self.warning_count,
                "indeterminate": self.indeterminate_count,
            },
            "signals": [s.to_dict() for s in self.signals],
            "reason": self.reason,
        }


# ---------------------------------------------------------------- 核心计算


def compute_z(value: float, mean: float, std: Optional[float]) -> Optional[float]:
    """z = (value - mean) / std；std 缺失或≈0 时返回 None（不可计算）。

    修掉的旧硬伤：baseline_personal.py 在 std==0 时把 z_score 设成 999.0，
    使 |z|>3 恒成立 → 必然 severity="danger"。历史会话里图谱指标常常恒定
    （7 条样本下极常见），等于把"数据没变化"渲染成"高危"。
    """
    if std is None or std <= 1e-9:
        return None
    return (value - mean) / std


def risk_from_z(z: Optional[float], direction: Direction) -> Optional[float]:
    """把带符号 z 折算成"风险方向上的偏离量"，越大越糟。"""
    if z is None:
        return None
    if direction is Direction.HIGH_IS_GOOD:
        return -z          # 下降才是风险
    if direction is Direction.HIGH_IS_BAD:
        return z           # 上升才是风险
    return abs(z)          # TWO_SIDED


def assess_signal(
    sig: Signal,
    baselines: Dict[str, BaselineStats],
    cfg: TierConfig = TierConfig(),
) -> SignalAssessment:
    base = baselines.get(sig.name)

    if sig.value is None:
        return SignalAssessment(sig.name, None, sig.direction, None, None,
                                None, None, Severity.INDETERMINATE, "no_value")
    if base is None:
        return SignalAssessment(sig.name, sig.value, sig.direction, None, None,
                                None, None, Severity.INDETERMINATE, "no_baseline")
    if base.n is not None and base.n < cfg.min_baseline_samples:
        return SignalAssessment(
            sig.name, sig.value, sig.direction, base.mean, base.std,
            None, None, Severity.INDETERMINATE,
            f"baseline_n={base.n}<{cfg.min_baseline_samples}", n=base.n,
        )

    z = compute_z(sig.value, base.mean, base.std)
    if z is None:
        return SignalAssessment(sig.name, sig.value, sig.direction, base.mean, base.std,
                                None, None, Severity.INDETERMINATE, "std_zero", n=base.n)

    risk = risk_from_z(z, sig.direction)
    if risk >= cfg.danger_z:
        sev = Severity.DANGER
    elif risk >= cfg.warning_z:
        sev = Severity.WARNING
    else:
        sev = Severity.NORMAL
    return SignalAssessment(sig.name, sig.value, sig.direction, base.mean, base.std,
                            round(z, 4), round(risk, 4), sev, "", n=base.n)


def vote_tier(
    assessments: Sequence[SignalAssessment],
    cfg: TierConfig = TierConfig(),
) -> TierResult:
    """按维度计票决定 tier。不使用任何加权求和。"""
    usable = [a for a in assessments if a.severity is not Severity.INDETERMINATE]
    danger = sum(1 for a in usable if a.severity is Severity.DANGER)
    warning = sum(1 for a in usable if a.severity is Severity.WARNING)
    indet = len(assessments) - len(usable)

    if len(usable) < cfg.min_usable_signals:
        return TierResult(Tier.INSUFFICIENT_DATA, "", list(assessments),
                          len(usable), danger, warning, indet,
                          f"usable={len(usable)}<{cfg.min_usable_signals}")

    # 基线样本量门槛：n 过小时 danger_z 结构上不可达，出档会产生假"绿"。
    ns = [a.n for a in usable if a.n is not None]
    if ns and min(ns) < cfg.min_usable_samples:
        return TierResult(Tier.INSUFFICIENT_DATA, "", list(assessments),
                          len(usable), danger, warning, indet,
                          f"baseline_n={min(ns)}<{cfg.min_usable_samples} "
                          f"(max_attainable_z={max_attainable_z(min(ns)):.2f}"
                          f"<danger_z={cfg.danger_z})")

    if danger == 0 and warning == 0:
        return TierResult(Tier.GREEN, "", list(assessments),
                          len(usable), danger, warning, indet, "no_deviation")

    if danger >= 2:
        return TierResult(Tier.RED, "", list(assessments),
                          len(usable), danger, warning, indet,
                          f"danger={danger}>=2")

    if danger == 1:
        if not cfg.red_requires_corroboration:
            return TierResult(Tier.RED, "", list(assessments),
                              len(usable), danger, warning, indet,
                              "danger=1, corroboration_off")
        # 单个 danger 一律封顶在琥珀：RED 必须有第二个独立维度佐证。
        # 比旧实现更保守——旧 danger*25 单维只能到 25 分（关注），
        # 但 1 danger + 1 warning 就到 35，1+2 到 45，实际是渐进升红，
        # 与"单维孤立不升级"的意图不一致。这里显式收敛为一条规则。
        return TierResult(Tier.AMBER, "", list(assessments),
                          len(usable), danger, warning, indet,
                          f"danger=1 (+warning={warning}) without 2nd danger")

    # danger == 0
    if warning >= 3:
        return TierResult(Tier.RED, "", list(assessments),
                          len(usable), danger, warning, indet, f"warning={warning}>=3")
    return TierResult(Tier.AMBER, "", list(assessments),
                      len(usable), danger, warning, indet, f"warning={warning}")


def evaluate_tier(
    signals: Sequence[Signal],
    baselines: Dict[str, BaselineStats],
    cfg: TierConfig = TierConfig(),
    config_version: str = "tier-v0.1-uncalibrated",
) -> TierResult:
    """唯一对外入口：一组当前信号 + 个人基线 → 分层结果。"""
    assessments = [assess_signal(s, baselines, cfg) for s in signals]
    result = vote_tier(assessments, cfg)
    return TierResult(
        tier=result.tier,
        config_version=config_version,
        signals=result.signals,
        usable_count=result.usable_count,
        danger_count=result.danger_count,
        warning_count=result.warning_count,
        indeterminate_count=result.indeterminate_count,
        reason=result.reason,
    )


# ------------------------------------------------- 由旧 deviation 结构适配


def evaluate_from_deviation(
    deviation: Dict[str, object],
    directions: Dict[str, Direction],
    cfg: TierConfig = TierConfig(),
    config_version: str = "tier-v0.1-legacy-graph",
) -> TierResult:
    """直接吃 ``check_personal_deviation`` 的返回值，不重算 z。

    过渡期用：baseline_personal 尚未改吐 ``indeterminate`` 之前，这里把
    ``std==0`` 造成的 z=±999 识别出来并降级为不可计算，避免虚报 danger。
    """
    raw_dims: List[Dict[str, object]] = list(deviation.get("dimensions") or [])  # type: ignore[arg-type]
    has_baseline = bool(deviation.get("has_baseline"))

    if not has_baseline or not raw_dims:
        return TierResult(Tier.INSUFFICIENT_DATA, config_version, [],
                          0, 0, 0, len(raw_dims), "no_baseline")

    assessments: List[SignalAssessment] = []
    for d in raw_dims:
        name = str(d.get("name"))
        direction = directions.get(name, Direction.HIGH_IS_GOOD)
        z_raw = d.get("z_score")
        std = d.get("std")
        value = d.get("current")
        mean = d.get("baseline")

        z: Optional[float] = float(z_raw) if isinstance(z_raw, (int, float)) else None
        std_f: Optional[float] = float(std) if isinstance(std, (int, float)) else None

        if z is None or abs(z) >= 900.0:        # ← 旧的 999 哨兵值
            assessments.append(SignalAssessment(
                name, float(value) if isinstance(value, (int, float)) else None,
                direction,
                float(mean) if isinstance(mean, (int, float)) else None,
                std_f, None, None, Severity.INDETERMINATE, "legacy_std_zero_sentinel"))
            continue

        risk = risk_from_z(z, direction)
        if risk >= cfg.danger_z:
            sev = Severity.DANGER
        elif risk >= cfg.warning_z:
            sev = Severity.WARNING
        else:
            sev = Severity.NORMAL
        assessments.append(SignalAssessment(
            name, float(value) if isinstance(value, (int, float)) else None, direction,
            float(mean) if isinstance(mean, (int, float)) else None, std_f,
            round(z, 4), round(risk, 4), sev, ""))

    result = vote_tier(assessments, cfg)
    return TierResult(result.tier, config_version, result.signals, result.usable_count,
                      result.danger_count, result.warning_count,
                      result.indeterminate_count, result.reason)


# ------------------------------------------------------ 指南对齐的行动建议
# ⚠ 下列截断值来自二手转述，进正式材料前必须回溯原始指南卷期/DOI 核对。
#   未核对前，next_step 只用于内部提示与 Demo 文案，不得作为临床建议输出。

AD8_CUTOFF_REACH_ASSESS = 2      # AD-8 ≥2 → 建议进入他评（MoCA）
AD8_CUTOFF_REFER_1_WEEK = 4      # AD-8 ≥4 → 一周内转记忆门诊
MOCA_CUTOFF_REFER_1_WEEK = 18    # MoCA ≤18 → 一周内转记忆门诊


def next_step(
    result: TierResult,
    ad8_score: Optional[int] = None,
    moca_score: Optional[int] = None,
) -> Dict[str, str]:
    """把分层结果 + 量表分数映射为下一步。量表指征优先于叙事分层。"""
    if ad8_score is not None and ad8_score >= AD8_CUTOFF_REFER_1_WEEK:
        return {"code": "memory_clinic_within_1_week",
                "label": "建议一周内至记忆门诊就诊",
                "basis": f"AD-8={ad8_score}≥{AD8_CUTOFF_REFER_1_WEEK}"}
    if moca_score is not None and moca_score <= MOCA_CUTOFF_REFER_1_WEEK:
        return {"code": "memory_clinic_within_1_week",
                "label": "建议一周内至记忆门诊就诊",
                "basis": f"MoCA={moca_score}≤{MOCA_CUTOFF_REFER_1_WEEK}"}
    if ad8_score is not None and ad8_score >= AD8_CUTOFF_REACH_ASSESS:
        return {"code": "moca_referred",
                "label": "建议完成一次 MoCA 他评",
                "basis": f"AD-8={ad8_score}≥{AD8_CUTOFF_REACH_ASSESS}"}

    if result.tier is Tier.RED:
        return {"code": "specialist_review_suggested",
                "label": "叙事多维度持续偏离，建议专科评估",
                "basis": result.reason}
    if result.tier is Tier.AMBER:
        return {"code": "short_interval_rescreen",
                "label": "建议缩短复评间隔并继续观察",
                "basis": result.reason}
    if result.tier is Tier.INSUFFICIENT_DATA:
        return {"code": "build_baseline",
                "label": "记录量不足以建立个人基线，先积累观察",
                "basis": result.reason}
    return {"code": "continue_observing", "label": "维持日常记录", "basis": result.reason}
