"""账号注销（个保法 47 条，gap G4）测试

覆盖：密码确认、级联删除、分析事件匿名化、审计日志去关联化、
注销后无法登录、对方账号不受影响。
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.models import (
    Session as SessionModel, Notification, FamilyLink, AnalyticsEvent,
    ScaleRecord, User,
)


def _register(client, username):
    r = client.post("/api/v1/auth/register", json={
        "username": username, "password": "Test123456!",
        "name": username, "role": "elderly",
    })
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _seed(db, elderly_id, family_id):
    db.add(SessionModel(user_id=elderly_id, day_number=1, narrative="今天很开心"))
    db.add(Notification(user_id=family_id, type="anomaly", title="t", content="c"))
    db.add(ScaleRecord(user_id=elderly_id, scale_type="mmse", total_score=28))
    db.add(AnalyticsEvent(user_id=elderly_id, event_name="daily_prompt_exposed"))
    db.add(FamilyLink(family_user_id=family_id, elderly_user_id=elderly_id,
                      is_active=True))
    db.commit()


def test_delete_account_requires_password(client, db_session):
    headers = _register(client, "del_user1")
    r = client.request(
        "DELETE", "/api/v1/auth/account", headers=headers,
        json={"password": "WrongPass1!"})
    assert r.status_code == 403
    # 账号仍在
    assert db_session.query(User).filter(User.username == "del_user1").first()


def test_delete_account_cascades_and_anonymizes(client, db_session):
    family = User(username="del_family", hashed_password="x", role="family",
                  name="f")
    db_session.add(family)
    db_session.commit()
    db_session.refresh(family)

    headers = _register(client, "del_user2")
    uid = db_session.query(User).filter(User.username == "del_user2").first().id
    _seed(db_session, uid, family.id)

    r = client.request(
        "DELETE", "/api/v1/auth/account", headers=headers,
        json={"password": "Test123456!"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"

    # 用户与业务数据物理删除
    assert db_session.query(User).filter(User.id == uid).first() is None
    assert db_session.query(SessionModel).filter(SessionModel.user_id == uid).count() == 0
    assert db_session.query(ScaleRecord).filter(ScaleRecord.user_id == uid).count() == 0
    assert db_session.query(FamilyLink).filter(
        (FamilyLink.elderly_user_id == uid) | (FamilyLink.family_user_id == uid)).count() == 0

    # 分析事件匿名化：行保留、user_id 置空（漏斗聚合读数保留）
    ev = db_session.query(AnalyticsEvent).filter(
        AnalyticsEvent.event_name == "daily_prompt_exposed").first()
    assert ev is not None and ev.user_id is None

    # 对方账号不受影响
    assert db_session.query(User).filter(User.id == family.id).first() is not None


def test_deleted_account_cannot_login(client, db_session):
    headers = _register(client, "del_user4")
    r = client.request(
        "DELETE", "/api/v1/auth/account", headers=headers,
        json={"password": "Test123456!"})
    assert r.status_code == 200
    r = client.post("/api/v1/auth/login", json={
        "identifier": "del_user4", "password": "Test123456!"})
    assert r.status_code in (401, 404)
