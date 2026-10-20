# ============ 试点周表导出（纯逻辑，不碰 DB）===========
"""把会话按自然周聚合成试点验收要的宽表。

两个容易出错的前提，先在代码里钉死：

1) 周分桶用本地时区而不是 UTC。DB 的 created_at 存 UTC，而老人作息按本地时间；
   用 UTC 切周会把周日 08:00 之前的记录错分到上一周（+08:00 时差 8 小时）。
   这里用固定偏移，中国大陆无夏令时。

2) 有效周计数**不需要解密**：它只依赖 low_confidence 与 asr_* 列。
   但"解不开密文的会话"会在真实特征计算时被剔除（见 narrative_text.py），
   所以若不检查，周表会把"其实算不出特征"的会话算进数据密度里，虚报进度。
   因此有 --check-decrypt 开关，且未检查时在 CSV 里显式写 decrypt_checked=0，
   让盲区可见而不是被默默忽略。

口径歧义也在字段名上讲清楚：complete_days 的分母是"该用户首次记录之日起的天数"，
不是日历整周天数，所以新用户第一周的完成率会偏低，这是预期。
"""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

DEFAULT_TZ_OFFSET_MINUTES = 8 * 60          # Asia/Shanghai，无夏令时
MIN_SESSIONS_PER_WEEK = 3                   # 与基线侧同一口径，改这里要同步改那边


def _local(dt: Optional[datetime], offset_minutes: int) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)      # 库里按 UTC 存，naive 视为 UTC
    return dt.astimezone(timezone(timedelta(minutes=offset_minutes)))


def week_of(day: date) -> Dict[str, str]:
    y, w, _ = day.isocalendar()
    monday = day - timedelta(days=day.weekday())
    return {"iso_week": f"{y}-W{w:02d}", "week_start": monday.isoformat()}


def _countable(session) -> bool:
    """NULL 视为未知即保留；只有明确 True 才剔除（与 build_personal_baseline 一致）"""
    return session.get("low_confidence") is not True


def build_week_rows(
    sessions: Iterable[Dict],
    period_end: date,
    tz_offset_minutes: int = DEFAULT_TZ_OFFSET_MINUTES,
    period_start: Optional[date] = None,
    decrypt_checker=None,
) -> List[Dict]:
    """sessions: [{user_id, created_at(datetime), low_confidence, asr_provider, ...}]

    decrypt_checker: 可选 callable(session) -> bool（True 表示解不开）。
    不传则不检查，CSV 的 decrypt_checked 记 0。
    """
    buckets: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
    first_seen: Dict[str, datetime] = {}

    for raw in sessions:
        local = _local(raw.get("created_at"), tz_offset_minutes)
        if local is None:
            continue
        uid = raw["user_id"]
        d = local.date()
        if period_start and d < period_start:
            continue
        if d > period_end:
            continue
        if uid not in first_seen or local < first_seen[uid]:
            first_seen[uid] = local
        wk = week_of(d)["iso_week"]
        buckets[uid][wk].append(dict(raw, _local_dt=local, _date=d))

    rows: List[Dict] = []
    for uid in sorted(buckets):
        # 该用户从首次记录那天起才该被要求记录，避免把入职前的空白算成不依从
        user_start = max(first_seen[uid].date(), period_start) if period_start else first_seen[uid].date()
        for wk in sorted(buckets[uid]):
            items = buckets[uid][wk]
            monday = date.fromisoformat(week_of(items[0]["_date"])["week_start"])
            sunday = monday + timedelta(days=6)
            # 分母只数落在观察范围内的天：首周与末周都是残缺周
            lo = max(monday, user_start)
            hi = min(sunday, period_end)
            expected = (hi - lo).days + 1 if hi >= lo else 0

            days = {it["_date"] for it in items}
            total = len(items)
            lowc = sum(1 for it in items if it.get("low_confidence") is True)
            unknown = sum(1 for it in items if it.get("low_confidence") is None)
            usable = sum(1 for it in items if _countable(it))
            dec_fail = 0
            if decrypt_checker:
                dec_fail = sum(1 for it in items if decrypt_checker(it))
                usable -= dec_fail        # 解不开的不进特征，不算进有效数据

            # 只有在明确标注 provider_missing_after_asr 时才计入，避免把
            # "0017 之前的存量记录（该列全 NULL）"误报成"ASR 全都失败了"
            asr_fail = sum(1 for it in items if it.get("provider_missing_after_asr"))
            no_narrative = sum(1 for it in items if not it.get("has_narrative", True))
            rate = (len(days) / expected) if expected > 0 else 0.0

            rows.append({
                "user_id": uid,
                "iso_week": wk,
                "week_start": monday.isoformat(),
                "expected_days": expected,
                "recorded_days": len(days),
                "completion_rate": round(rate, 4),
                "sessions_total": total,
                "no_narrative": no_narrative,
                "sessions_countable": usable,
                "low_confidence_count": lowc,
                "low_confidence_unknown": unknown,
                "decrypt_failed": dec_fail,
                "asr_failed": asr_fail,
                "valid_week": int(usable >= MIN_SESSIONS_PER_WEEK),
                # 溯源列全 NULL 的周：low_confidence 与 provider 都无值，
                # 低置信率既不是 0% 也不是 100%，是"没测"。不标出来就会被读成"没有失败"
                "provenance_unlabeled": int(
                    total > 0 and all(it.get("low_confidence") is None for it in items)
                    and all(it.get("asr_provider") is None for it in items)),
                "decrypt_checked": int(decrypt_checker is not None),
            })
    return rows


COLUMNS = [
    "user_id", "iso_week", "week_start", "expected_days", "recorded_days",
    "completion_rate", "sessions_total", "sessions_countable", "low_confidence_count",
    "low_confidence_unknown", "no_narrative", "decrypt_failed", "asr_failed", "valid_week",
    "provenance_unlabeled", "decrypt_checked",
]
