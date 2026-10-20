"""P2 试点周表导出：分桶、NULL 语义、对账、幂等"""
from datetime import date, datetime, timezone

import pytest

from app.services.pilot_export import COLUMNS, build_week_rows
from scripts.export_pilot_weeks import _reconcile, reconcile_with_default_local

UTC = timezone.utc


def _s(uid, dt, low=None, provider="vosk"):
    return {"user_id": uid, "created_at": dt, "low_confidence": low,
            "asr_provider": provider, "is_recorded": True}


# ---------------------------------------------------------------- 时区分桶

def test_sunday_evening_utc_lands_in_next_local_week():
    """2026-10-18 17:00Z = 2026-10-19 01:00 +08（周一），属 2026-W43。
    若按 UTC 切周会错分到 W42。"""
    rows = build_week_rows([_s("u1", datetime(2026, 10, 18, 17, 0, tzinfo=UTC))],
                           period_end=date(2026, 10, 31))
    assert len(rows) == 1
    assert rows[0]["iso_week"] == "2026-W43"
    assert rows[0]["week_start"] == "2026-10-19"


def test_local_monday_just_after_midnight_utc_belongs_to_new_week():
    """2026-10-26 00:30 +08 = 2026-10-25 16:30Z（周日），应属 W44 而非 W43。"""
    rows = build_week_rows([_s("u1", datetime(2026, 10, 25, 16, 30, tzinfo=UTC))],
                           period_end=date(2026, 10, 31))
    assert rows[0]["iso_week"] == "2026-W44"


def test_naive_utc_bucketing_would_disagree_regression_lock():
    """显式记录这个 bug 的形态：同一时刻按 UTC 切周会得到另一个周号。
    若哪天有人把时区偏移默认改成 0，上面的用例应失败，这条用于说明差异来源。"""
    dt = datetime(2026, 10, 18, 17, 0, tzinfo=UTC)
    local_week = build_week_rows([_s("u1", dt)], period_end=date(2026, 10, 31))[0]["iso_week"]
    utc_week = dt.astimezone(timezone.utc).isocalendar()
    assert f"{utc_week[0]}-W{utc_week[1]:02d}" == "2026-W42"
    assert local_week == "2026-W43"
    assert local_week != f"{utc_week[0]}-W{utc_week[1]:02d}"


# ---------------------------------------------------------------- NULL 语义

def test_low_confidence_null_kept_true_excluded():
    items = [_s("u1", datetime(2026, 10, 19 + i % 4, 9, tzinfo=UTC), low=v)
             for i, v in enumerate([True, True, None, None, False, False])]
    rows = build_week_rows(items, period_end=date(2026, 10, 31))
    r = rows[0]
    assert r["sessions_total"] == 6
    assert r["low_confidence_count"] == 2
    assert r["low_confidence_unknown"] == 2
    assert r["sessions_countable"] == 4        # NULL 保留，只有 True 被剔
    assert r["valid_week"] == 1


def test_only_low_confidence_week_is_not_valid():
    items = [_s("u1", datetime(2026, 10, 19 + i, 9, tzinfo=UTC), low=True) for i in range(4)]
    rows = build_week_rows(items, period_end=date(2026, 10, 31))
    assert rows[0]["sessions_countable"] == 0
    assert rows[0]["valid_week"] == 0


def test_decrypt_checker_subtracts_from_countable():
    items = [_s("u1", datetime(2026, 10, 19 + i, 9, tzinfo=UTC)) for i in range(4)]
    rows = build_week_rows(items, period_end=date(2026, 10, 31))
    assert rows[0]["decrypt_checked"] == 0
    assert rows[0]["decrypt_failed"] == 0

    hits = build_week_rows(items, period_end=date(2026, 10, 31),
                           decrypt_checker=lambda it: it["created_at"].day >= 21)
    assert hits[0]["decrypt_checked"] == 1
    assert hits[0]["decrypt_failed"] == 2
    assert hits[0]["sessions_countable"] == 2   # 解不开的不算进有效数据


# ---------------------------------------------------------------- 残缺周边界

def test_first_week_denominator_starts_at_first_record():
    """首次记录在周三，则首周分母是 5 天而非 7 天，避免把没参与的日期算成不依从。"""
    items = [_s("u1", datetime(2026, 10, 21, 9, tzinfo=UTC)),        # 周三
             _s("u1", datetime(2026, 10, 22, 9, tzinfo=UTC))]        # 周四
    rows = build_week_rows(items, period_end=date(2026, 10, 25))
    assert rows[0]["expected_days"] == 5
    assert rows[0]["recorded_days"] == 2
    assert rows[0]["completion_rate"] == pytest.approx(0.4)


def test_partial_last_week_denominator_capped_at_period_end():
    items = [_s("u1", datetime(2026, 10, 26, 9, tzinfo=UTC))]
    rows = build_week_rows(items, period_end=date(2026, 10, 27))
    assert rows[0]["expected_days"] == 2
    assert rows[0]["completion_rate"] == pytest.approx(0.5)


# ---------------------------------------------------------------- 对账与幂等

def test_reconcile_matches_and_detects_tampering():
    items = [_s("u1", datetime(2026, 10, 19 + i % 12, 9, tzinfo=UTC)) for i in range(20)]
    items += [_s("u2", datetime(2026, 10, 20, 9, tzinfo=UTC))]
    rows = build_week_rows(items, period_end=date(2026, 11, 1))
    assert _reconcile(items, rows, 8 * 60, None, date(2026, 11, 1)) == []

    tampered = [dict(r) for r in rows]
    tampered[0]["sessions_total"] += 1
    diffs = _reconcile(items, tampered, 8 * 60, None, date(2026, 11, 1))
    assert diffs, "被篡改后对账仍通过，说明对账没起作用"


def test_reconcile_catches_wrong_timezone_bucketing():
    """把偏移改成 0（UTC 切周），以本地为基准的对账必须失败。

    刻意用**跨日界的时刻**（2026-10-18 17:00Z = 本地 10-19 周一）：
    若像早先那版测试一样把所有会话都放在 09:00Z（本地 17:00，日期与 UTC 完全相同），
    两套分桶结果必然一致，对账通过也证明不了任何事 —— 这是我自己踩过的坑，
    留在这里防止再次写出"看着有效其实恒真"的对账。
    """
    items = [
        _s("u1", datetime(2026, 10, 18, 17, 0, tzinfo=UTC)),   # 本地 W43 / UTC W42
        _s("u1", datetime(2026, 10, 19, 17, 30, tzinfo=UTC)),  # 本地 10-20 W43 / UTC 10-19 W43
        _s("u1", datetime(2026, 10, 20, 16, 0, tzinfo=UTC)),   # 本地 10-21 W43 / UTC 10-20 W43
    ]
    utc_rows = build_week_rows(items, period_end=date(2026, 10, 31), tz_offset_minutes=0)
    local_rows = build_week_rows(items, period_end=date(2026, 10, 31))
    # UTC 切法：17:00Z 周日那条落 W42；本地切法下它属 10-19 周一即 W43
    assert [r["sessions_total"] for r in utc_rows] == [1, 2]
    assert [r["sessions_total"] for r in local_rows] == [3]
    assert local_rows != utc_rows, "两套分桶没差异，测试数据无效"

    diffs = reconcile_with_default_local(items, utc_rows, 0, None, date(2026, 10, 31))
    assert diffs, "UTC 分桶未被本地对账抓住，说明对账是同义反复"
    ok = reconcile_with_default_local(items, local_rows, 8 * 60, None, date(2026, 10, 31))
    assert ok == [], "正常路径不应报错: " + str(ok)


def test_provenance_unlabeled_flag_for_pre_0017_data():
    """0017 之前的存量记录：溯源列全 NULL，低置信率既不是 0% 也不是 100%，是没测。"""
    items = [_s("u1", datetime(2026, 10, 19 + i, 9, tzinfo=UTC), low=None, provider=None)
             for i in range(4)]
    rows = build_week_rows(items, period_end=date(2026, 10, 31))
    assert rows[0]["low_confidence_count"] == 0
    assert rows[0]["provenance_unlabeled"] == 1, "没标记为未标注，会被读成零失败"


def test_asr_failed_not_confused_with_legacy_null_provider():
    """存量记录 asr_provider 全 NULL，不得被算成 ASR 失败。"""
    legacy = [_s("u1", datetime(2026, 10, 19 + i, 9, tzinfo=UTC), provider=None)
              for i in range(4)]
    assert build_week_rows(legacy, period_end=date(2026, 10, 31))[0]["asr_failed"] == 0

    labeled_missing = [dict(_s("u1", datetime(2026, 10, 19 + i, 9, tzinfo=UTC),
                               low=False), provider_missing_after_asr=True)
                       for i in range(4)]
    assert build_week_rows(labeled_missing,
                           period_end=date(2026, 10, 31))[0]["asr_failed"] == 4


def test_output_is_deterministic_and_column_complete():
    items = [_s("u%d" % (i % 2), datetime(2026, 10, 19 + i, 9, tzinfo=UTC)) for i in range(10)]
    a = build_week_rows(items, period_end=date(2026, 10, 31))
    b = build_week_rows(items, period_end=date(2026, 10, 31))
    assert a == b
    assert a == sorted(a, key=lambda r: (r["user_id"], r["week_start"]))
    for r in a:
        assert set(COLUMNS) <= set(r)


def test_row_sum_equals_input_count_no_loss_no_double():
    items = [_s("u1", datetime(2026, 10, 12 + i, 9, tzinfo=UTC)) for i in range(20)]
    rows = build_week_rows(items, period_end=date(2026, 10, 31))
    assert sum(r["sessions_total"] for r in rows) == 20
    assert len({r["iso_week"] for r in rows}) == 3      # W42/W43/W44
