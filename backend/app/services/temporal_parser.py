# ============ 时间实体解析服务 ============
"""从中文叙事文本中提取时间表达并解析为具体日期/偏移。

支持相对时间（昨天、上周、上个月）和绝对日期（X月X日），
为会话自动推断 ``day_number`` 提供依据。
"""

import re
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional

logger = logging.getLogger("cognitive_garden")

# 中文数字映射（支持 1-12 月、1-31 日）
_CN_NUM: Dict[str, int] = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
    "二十一": 21, "二十二": 22, "二十三": 23, "二十四": 24, "二十五": 25,
    "二十六": 26, "二十七": 27, "二十八": 28, "二十九": 29, "三十": 30,
    "三十一": 31,
}

# 相对时间正则 → day_offset（负数表示过去）
_RELATIVE_PATTERNS: List[tuple] = [
    (re.compile(r"前天"), -2),
    (re.compile(r"昨天"), -1),
    (re.compile(r"上周[一二三四五六日]?|上个星期[一二三四五六日]?"), -7),
    (re.compile(r"上个月"), -30),
]

# "X月X日" 正则（阿拉伯数字或中文数字）
_DATE_PATTERN = re.compile(
    r"([0-9]{1,2}|[一二三四五六七八九十十一十二]{1,2})\s*月\s*([0-9]{1,2}|[一二三四五六七八九十]{1,2})\s*日"
)


def _parse_cn_number(s: str) -> Optional[int]:
    """将中文数字或阿拉伯数字转为整数。"""
    try:
        return int(s)
    except ValueError:
        return _CN_NUM.get(s)


def _resolve_month_day(month: int, day: int, now: date) -> Optional[date]:
    """根据月/日推断具体年份（与当前日期比较）。

    若月份大于当前月，则推断为去年；
    若月份等于当前月但日期大于当前日，也推断为去年。
    """
    if not (1 <= month <= 12) or not (1 <= day <= 31):
        return None
    year = now.year
    if month > now.month:
        year -= 1
    elif month == now.month and day > now.day:
        year -= 1
    try:
        return date(year, month, day)
    except ValueError:
        return None


def extract_temporal_references(text: str) -> List[Dict[str, Any]]:
    """提取文本中的中文时间表达并解析为具体日期。

    支持模式：
    - 相对时间：昨天、前天、上周/上个星期、上个月
    - 绝对日期：X月X日（中文或阿拉伯数字）

    Args:
        text: 用户输入的叙事文本。

    Returns:
        每个元素包含 ``entity``（匹配文本）、``resolved_date``（datetime）、
        ``confidence``（0.0-1.0）、``day_offset``（相对于今天的天数差）。
    """
    results: List[Dict[str, Any]] = []
    now = datetime.now().date()
    scanned_positions: set = set()

    # 1. 相对时间匹配
    for pattern, day_offset in _RELATIVE_PATTERNS:
        for match in pattern.finditer(text):
            pos = match.start()
            if pos in scanned_positions:
                continue
            scanned_positions.add(pos)
            entity = match.group(0)
            resolved_date = datetime.combine(
                now + timedelta(days=day_offset), datetime.min.time()
            )
            confidence = 0.95 if day_offset in (-1, -2) else 0.85
            results.append({
                "entity": entity,
                "resolved_date": resolved_date.isoformat(),
                "confidence": confidence,
                "day_offset": day_offset,
            })

    # 2. "X月X日" 匹配
    for match in _DATE_PATTERN.finditer(text):
        pos = match.start()
        if pos in scanned_positions:
            continue
        scanned_positions.add(pos)
        entity = match.group(0)
        month_str = match.group(1)
        day_str = match.group(2)
        month = _parse_cn_number(month_str)
        day = _parse_cn_number(day_str)
        if month is None or day is None:
            continue
        resolved = _resolve_month_day(month, day, now)
        if resolved:
            day_offset = (resolved - now).days
            results.append({
                "entity": entity,
                "resolved_date": datetime.combine(resolved, datetime.min.time()).isoformat(),
                "confidence": 0.8,
                "day_offset": day_offset,
            })

    # 按 resolved_date 升序排列
    results.sort(key=lambda x: x["resolved_date"])
    return results


def resolve_day_number(
    temporal_refs: List[Dict[str, Any]],
    current_date: datetime,
) -> Optional[int]:
    """根据时间引用计算 ``day_number`` 偏移。

    取所有引用中最小（最历史）的 ``day_offset``，若其为负则返回。

    Args:
        temporal_refs: ``extract_temporal_references`` 的返回值。
        current_date: 当前真实日期（datetime），用于计算无 ``day_offset`` 的引用。

    Returns:
        负整数偏移（如 -1 表示昨天），或 ``None``（无历史时间引用）。
    """
    if not temporal_refs:
        return None

    offsets: List[int] = []
    for ref in temporal_refs:
        # 优先使用已解析的 day_offset
        if "day_offset" in ref:
            offsets.append(ref["day_offset"])
            continue
        # 否则从 resolved_date 计算（兼容 datetime/date/ISO 字符串）
        resolved = ref.get("resolved_date")
        if isinstance(resolved, str):
            try:
                resolved = datetime.fromisoformat(resolved)
            except ValueError:
                continue
        if isinstance(resolved, datetime):
            delta = (resolved.date() - current_date.date()).days
            offsets.append(delta)
        elif isinstance(resolved, date):
            delta = (resolved - current_date.date()).days
            offsets.append(delta)

    if not offsets:
        return None

    min_offset = min(offsets)
    return min_offset if min_offset < 0 else None
