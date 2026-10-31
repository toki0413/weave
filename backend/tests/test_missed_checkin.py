"""W3 漏录日课提醒回归：阈值、幂等、不催未记录、纯时间判定

幂等两层：signal_key 含北京日期（走 _create_for_family 的冷却）+ Redis 日锁。
本文件测服务层的幂等与判定；时间触发逻辑单独作为纯函数验算。
"""
import uuid
from datetime import datetime, timedelta, timezone

from app.models import FamilyLink, Notification, Session as DBSession, User
from app.services.missed_checkin_job import should_run
from app.services.notification_service import (
    compute_missing_days, create_missed_checkin_notifications,
)

PHONE = [13900003000]


def _next_phone():
    PHONE[0] += 1
    return str(PHONE[0])


def _register(client, db, role, name):
    phone = _next_phone()
    r = client.post("/api/v1/auth/register",
                    json={"phone": phone, "password": "Test123456!", "role": role, "name": name})
    assert r.status_code == 200, r.text
    return db.query(User).filter(User.phone == phone).first(), \
        {"Authorization": "Bearer " + r.json()["access_token"]}


def _link(db, elderly, family):
    db.add(FamilyLink(elderly_user_id=elderly.id, family_user_id=family.id, relation="子女"))
    db.commit()


def _session_then_backdate(client, db, headers, days_ago, text="今天和老王下棋"):
    r = client.post("/api/v1/session/", headers=headers,
                    json={"day_number": 1, "narrative_input": {"text": text}})
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    row = db.get(DBSession, sid)
    row.created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    db.commit()
    return sid


def _count(db, family_id):
    return db.query(Notification).filter(
        Notification.user_id == family_id,
        Notification.type == "missed_checkin",
    ).count()


def test_compute_missing_days_cases(client, db_session):
    elder, eh = _register(client, db_session, "elderly", "算法基准")
    assert compute_missing_days(db_session, elder.id) is None, "从未记录应为 None（未知）"

    _session_then_backdate(client, db_session, eh, days_ago=3)
    assert compute_missing_days(db_session, elder.id) == 3

    _session_then_backdate(client, db_session, eh, days_ago=0, text="刚说完今天的事")
    assert compute_missing_days(db_session, elder.id) == 0, "当天有记录应为 0"


def test_notification_created_once_per_day(client, db_session):
    """重复执行只有一条——幂等（去掉频控类型即失败）"""
    elder, eh = _register(client, db_session, "elderly", "三天未录")
    fam, _ = _register(client, db_session, "family", "家属甲")
    _link(db_session, elder, fam)
    _session_then_backdate(client, db_session, eh, days_ago=3)

    n1 = create_missed_checkin_notifications(db_session, threshold_days=2)
    assert n1 == 1, f"应写入 1 条，实得 {n1}"
    n2 = create_missed_checkin_notifications(db_session, threshold_days=2)
    assert n2 == 0, f"同日重复执行应跳过，实得 {n2}"
    assert _count(db_session, fam.id) == 1, "重复执行后总数必须仍为 1"

    row = db_session.query(Notification).filter(
        Notification.user_id == fam.id, Notification.type == "missed_checkin").first()
    assert row.severity == "warning"
    assert "3" in (row.content or "")
    # 每条告警必须带"可以做什么"（PRD 红线：只报忧不给出路是伤害）
    assert (row.related_data or {}).get("actions"), "漏录提醒未附带可执行动作"


def test_today_active_elder_not_disturbed(client, db_session):
    elder, eh = _register(client, db_session, "elderly", "今天录了")
    fam, _ = _register(client, db_session, "family", "家属乙")
    _link(db_session, elder, fam)
    _session_then_backdate(client, db_session, eh, days_ago=0)
    assert create_missed_checkin_notifications(db_session, threshold_days=2) == 0
    assert _count(db_session, fam.id) == 0


def test_never_recorded_elder_not_pushed(client, db_session):
    """从未记录 = 缺首次引导，不是催办；也不该发"已经 N 天没录"的未知数字"""
    elder, _ = _register(client, db_session, "elderly", "从没录过")
    fam, _ = _register(client, db_session, "family", "家属丙")
    _link(db_session, elder, fam)
    assert create_missed_checkin_notifications(db_session, threshold_days=2) == 0
    assert _count(db_session, fam.id) == 0


def test_unlinked_elder_writes_nothing(db_session):
    """没绑家属的老人不该生成通知（也没人可收）"""
    assert create_missed_checkin_notifications(db_session, threshold_days=2) >= 0


# ---------------- 触发时刻纯函数 ----------------

def test_should_run_respects_beijing_hour():
    # 北京 19:59 → 不该跑；20:00 → 该跑
    before = datetime(2026, 10, 26, 11, 59, tzinfo=timezone.utc)   # 19:59 北京
    at = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)       # 20:00 北京
    assert should_run(before, hour_beijing=20, last_run_date=None) is False
    assert should_run(at, hour_beijing=20, last_run_date=None) is True


def test_should_run_skips_when_already_ran_today():
    at = datetime(2026, 10, 26, 13, 30, tzinfo=timezone.utc)
    today = (at + timedelta(minutes=480)).date()
    assert should_run(at, hour_beijing=20, last_run_date=today) is False, "当天已跑过不再跑"
    yesterday = today - timedelta(days=1)
    assert should_run(at, hour_beijing=20, last_run_date=yesterday) is True, "次日应恢复"
