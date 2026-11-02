"""家属周摘要（gap G5）测试

覆盖：周聚合统计、本周零记录不发、同周幂等（6 天冷却）、
should_run_week 纯时间判定、摘要内容含计数。
"""
from datetime import datetime, time as dtime, timedelta, timezone

import pytest

from app.models import Session as DBSession, FamilyLink, User
from app.services.weekly_digest_job import (
    beijing_now, week_key_bj, should_run_week, collect_weekly_stats,
    create_weekly_digest_notifications,
)

BJ = timezone(timedelta(minutes=480))


def _mk_user(db, username, role="family"):
    u = User(username=username, hashed_password="x", role=role, name=username)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _add_session(db, user_id, created_utc, emotion=None):
    db.add(DBSession(user_id=user_id, day_number=1, narrative="x",
                     created_at=created_utc, emotion_label=emotion))


# ---------- 纯时间判定 ----------

def test_should_run_week_time_gate():
    # 2026-11-02 是周一；北京 09:00 还没到 10 点 → 不跑
    t = datetime(2026, 11, 2, 1, 0, tzinfo=timezone.utc)   # 北京 09:00
    assert should_run_week(t, 0, 10, None) is False
    # 北京 11:00 → 跑
    t = datetime(2026, 11, 2, 3, 0, tzinfo=timezone.utc)   # 北京 11:00
    assert should_run_week(t, 0, 10, None) is True
    # 同周已跑过 → 不再跑
    assert should_run_week(t, 0, 10, "2026-11-02") is False
    # 非配置日（周二）→ 不跑
    t = datetime(2026, 11, 3, 3, 0, tzinfo=timezone.utc)
    assert should_run_week(t, 0, 10, None) is False


def test_week_key_is_monday():
    # 周四（2026-11-05）的周 key 应是周一 2026-11-02
    t = datetime(2026, 11, 5, 3, 0, tzinfo=timezone.utc)
    assert week_key_bj(t) == "2026-11-02"


# ---------- 聚合 ----------

def test_collect_weekly_stats(db_session):
    u = _mk_user(db_session, "wd_elderly", role="elderly")
    now = datetime.now(timezone.utc)
    week_start = beijing_now().date() - timedelta(days=beijing_now().date().weekday())
    since_utc = datetime.combine(week_start, dtime.min, tzinfo=BJ).astimezone(timezone.utc)
    # 本周窗口内两条（一天消极）+ 上周一条（不计入）。窗口起点 +2h 保证
    # 即使今天是周一上午也落在窗口内。
    _add_session(db_session, u.id, now - timedelta(hours=1), "negative")
    _add_session(db_session, u.id, since_utc + timedelta(hours=2), "positive")
    _add_session(db_session, u.id, since_utc - timedelta(days=3), "negative")
    db_session.commit()

    stats = collect_weekly_stats(db_session, u.id, week_start)
    assert stats["record_count"] == 2
    assert stats["negative_days"] == 1
    assert 1 <= stats["active_days"] <= 2


# ---------- 通知生成 ----------

def test_weekly_digest_created_and_idempotent(db_session):
    elderly = _mk_user(db_session, "wd_e2", role="elderly")
    family = _mk_user(db_session, "wd_f2", role="family")
    db_session.add(FamilyLink(family_user_id=family.id,
                              elderly_user_id=elderly.id, is_active=True))
    _add_session(db_session, elderly.id,
                 datetime.now(timezone.utc) - timedelta(hours=1), "positive")
    db_session.commit()
    n = create_weekly_digest_notifications(db_session)
    assert n == 1
    # 同周再跑：6 天冷却挡住，不重复
    assert create_weekly_digest_notifications(db_session) == 0


def test_weekly_digest_skips_empty_week(db_session):
    elderly = _mk_user(db_session, "wd_e3", role="elderly")
    family = _mk_user(db_session, "wd_f3", role="family")
    db_session.add(FamilyLink(family_user_id=family.id,
                              elderly_user_id=elderly.id, is_active=True))
    # 只有上周的记录，本周零记录 → 不发
    _add_session(db_session, elderly.id,
                 datetime.now(timezone.utc) - timedelta(days=15))
    db_session.commit()
    assert create_weekly_digest_notifications(db_session) == 0


def test_weekly_digest_content_contains_counts(db_session):
    from app.models import Notification
    elderly = _mk_user(db_session, "wd_e4", role="elderly")
    family = _mk_user(db_session, "wd_f4", role="family")
    db_session.add(FamilyLink(family_user_id=family.id,
                              elderly_user_id=elderly.id, is_active=True))
    _add_session(db_session, elderly.id,
                 datetime.now(timezone.utc) - timedelta(hours=1), "positive")
    db_session.commit()
    create_weekly_digest_notifications(db_session)

    n = db_session.query(Notification).filter(
        Notification.type == "weekly_digest",
        Notification.user_id == family.id).first()
    assert n is not None
    assert "本周 TA 记录了 1 次回忆" in n.content
    assert n.related_data["record_count"] == 1
    assert n.related_data["week_start"]
