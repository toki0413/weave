"""试点周表导出 CLI

用法（backend/ 目录下）：
    python -m scripts.export_pilot_weeks --end 2026-11-15 --out pilot.csv
    python -m scripts.export_pilot_weeks --end 2026-11-15 --reconcile
    python -m scripts.export_pilot_weeks --end 2026-11-15 --check-decrypt

--reconcile 用一条**独立实现**（按周区间逐周过滤）复核周分桶结果，而不是再走
一遍同样的 isocalendar —— 复用同一套代码的对账只能证明"代码和自己一致"，
证明不了"分桶正确"。不一致即非零退出。

--check-decrypt 会真的尝试解密每条叙事。不开时 CSV 的 decrypt_checked=0，
把"没检查"这件事留在结果里，而不是让人以为 decrypt_failed=0 就是全都解得开。
"""
import argparse
import csv
import io
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from app.database import SessionLocal
from app.models import Session as DBSession
from app.services.pilot_export import COLUMNS, build_week_rows


def _to_local(dt, offset_minutes):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone(timedelta(minutes=offset_minutes)))


def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def reconcile_with_default_local(sessions, rows, offset_minutes,
                                 period_start, period_end, local_offset_minutes=8 * 60):
    """以本地时区（默认 +480）为独立基准复核主路径分桶。

    单独抽出这个入口，是为了让"主路径误用 UTC、对账用本地应当报错"这件事
    可被单元测试覆盖：否则 _reconcile 需要调用方记得传两个不同偏移，
    而 CLI 里传错了并不会被任何东西发现。
    """
    return _reconcile(sessions, rows, offset_minutes, period_start, period_end,
                      reconcile_offset_minutes=local_offset_minutes)


def _reconcile(sessions, rows, offset_minutes, period_start, period_end,
               reconcile_offset_minutes=None):
    """独立实现复核：先算出观察期覆盖了哪些周一，再按 [monday, monday+7) 逐周过滤。

    刻意不调用 week_of()/isocalendar()，避免与主路径共享同一个出错点。
    reconcile_offset_minutes 允许用**另一个时区偏移**复核：默认取本地 +480，
    于是主路径若误用 UTC 切周就会对不上。两者相同只能证明"代码和自己一致"，
    证明不了分桶正确。返回差异列表，空表示一致。
    """
    ro = offset_minutes if reconcile_offset_minutes is None else reconcile_offset_minutes
    first_monday = _monday_of(period_start or min(
        _to_local(s["created_at"], ro).date() for s in sessions))
    diffs = []
    weeks = []
    m = first_monday
    while m <= period_end:
        weeks.append(m)
        m += timedelta(days=7)

    built = {(r["user_id"], r["week_start"]): r for r in rows}
    for monday in weeks:
        lo = datetime.combine(monday, datetime.min.time())
        hi = lo + timedelta(days=7)
        counts = defaultdict(int)
        for s in sessions:
            local = _to_local(s["created_at"], ro)
            if local is None:
                continue
            if lo <= local.replace(tzinfo=None) < hi:
                counts[s["user_id"]] += 1
        for uid, cnt in counts.items():
            key = (uid, monday.isoformat())
            row = built.get(key)
            if row is None:
                diffs.append(f"缺行 {key} 独立计数={cnt}")
            elif row["sessions_total"] != cnt:
                diffs.append(f"{key} 主路径={row['sessions_total']} 独立={cnt}")
    # 反向：主路径多出来的周也要报
    for (uid, ws), row in built.items():
        if date.fromisoformat(ws) not in weeks and row["sessions_total"]:
            diffs.append(f"主路径多出周 {uid} {ws}")
    return diffs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", required=True, help="观察期结束日 YYYY-MM-DD（含，按本地时区）")
    ap.add_argument("--start", help="观察期开始日，默认从最早记录起")
    ap.add_argument("--out", default="-", help="CSV 路径，- 表示 stdout")
    ap.add_argument("--tz-offset-minutes", type=int, default=8 * 60)
    ap.add_argument("--reconcile", action="store_true")
    ap.add_argument("--reconcile-tz-offset-minutes", type=int, default=8 * 60,
                    help="对账用时区偏移，默认本地 +480；与主路径不同时即成交叉验证")
    ap.add_argument("--check-decrypt", action="store_true")
    args = ap.parse_args(argv)

    end = date.fromisoformat(args.end)
    start = date.fromisoformat(args.start) if args.start else None

    db = SessionLocal()
    try:
        query = db.query(DBSession)
        if start:
            # 边界换算回 UTC 再查，避免少取一天的记录
            start_utc = datetime.combine(start, datetime.min.time()).replace(
                tzinfo=timezone.utc) - timedelta(minutes=args.tz_offset_minutes)
            query = query.filter(DBSession.created_at >= start_utc)
        orm = query.order_by(DBSession.created_at.asc()).all()

        checker = None
        if args.check_decrypt:
            from app.services.narrative_text import decrypt_narrative, DECRYPT_FAILED

            def checker(item):
                row = item.get("row")
                if row is None:
                    return False
                nt = decrypt_narrative(row.narrative, row.user_id, bool(row.is_encrypted))
                return nt.state == DECRYPT_FAILED

        items = [{
            "user_id": s.user_id,
            "created_at": s.created_at,
            "low_confidence": s.low_confidence,
            "asr_provider": s.asr_provider,
            "is_recorded": True,
            "row": s,                       # checker 要用 ORM 对象取密文
        } for s in orm]

        if not items:
            print("无会话数据", file=sys.stderr)
            return 1

        rows = build_week_rows(items, period_end=end, period_start=start,
                               tz_offset_minutes=args.tz_offset_minutes,
                               decrypt_checker=checker)

        if args.reconcile:
            ro = args.reconcile_tz_offset_minutes
            if ro != args.tz_offset_minutes:
                print("主路径偏移 %d 与对账偏移 %d 不同，正在交叉验证"
                      % (args.tz_offset_minutes, ro), file=sys.stderr)
            diffs = _reconcile(items, rows, args.tz_offset_minutes, start, end,
                               reconcile_offset_minutes=ro)
            if diffs:
                print("对账失败：\n  " + "\n  ".join(diffs[:20]), file=sys.stderr)
                return 2
            print(f"对账通过：{len(rows)} 行逐周与独立实现一致", file=sys.stderr)

        buf = io.StringIO() if args.out == "-" else open(args.out, "w", encoding="utf-8", newline="")
        w = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
        if args.out == "-":
            sys.stdout.write(buf.getvalue())
        else:
            buf.close()
            print(f"已导出 {len(rows)} 行至 {args.out}", file=sys.stderr)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
