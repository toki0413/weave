"""本周记忆卡片 + 匿名公开埋点测试（K 因子增长回路）"""
import uuid

from app.models import FamilyLink, MemoryCardShare, Session as DBSession, User


def _register_user(client, phone, password="Test123456!", role="elderly", name=None):
    body = {"phone": phone, "password": password, "role": role}
    if name:
        body["name"] = name
    r = client.post("/api/v1/auth/register", json=body)
    assert r.status_code == 200, f"注册失败: {r.text}"
    token = r.json()["access_token"]
    return r.json(), {"Authorization": f"Bearer {token}"}


def _seed_elderly_with_session(db, username, name):
    user = User(id=str(uuid.uuid4()), username=username, hashed_password="x",
                role="elderly", name=name)
    db.add(user)
    db.commit()
    db.add(DBSession(
        user_id=user.id,
        day_number=1,
        narrative="今天在公园和老朋友散步，聊了很久",
        graph={"nodes": [
            {"id": "self", "type": "self", "label": "我", "weight": 9},
            {"id": "n1", "type": "person", "label": "老朋友", "weight": 3},
            {"id": "n2", "type": "place", "label": "公园", "weight": 2},
            {"id": "n3", "type": "event", "label": "散步", "weight": 1},
        ]},
        metrics={},
        health_score=82,
    ))
    db.commit()
    return user


# ========== 生成与公开读取 ==========
def test_generate_requires_family_role(client):
    _, headers = _register_user(client, "13900200001", role="elderly")
    r = client.post("/api/v1/card/generate", headers=headers)
    assert r.status_code == 403


def test_generate_without_link_404(client):
    _, headers = _register_user(client, "13900200002", role="family")
    r = client.post("/api/v1/card/generate", headers=headers)
    assert r.status_code == 404


def test_generate_and_public_read(client, db_session):
    elderly = _seed_elderly_with_session(db_session, "13900200003", "张大爷")
    _, fam_headers = _register_user(client, "13900200004", role="family", name="张小华")
    db_session.add(FamilyLink(elderly_user_id=elderly.id,
                              family_user_id=_family_id(db_session, "13900200004"),
                              relation="子女"))
    db_session.commit()

    r = client.post("/api/v1/card/generate", headers=fam_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    payload = data["payload"]
    assert payload["record_count"] == 1
    assert payload["total_chars"] > 0
    assert payload["trend_level"] == "状态稳定"
    # 脱敏边界：top_entities 排除 self；payload 绝不含叙事原文
    labels = [e["label"] for e in payload["top_entities"]]
    assert "老朋友" in labels and "我" not in labels
    assert "今天在公园和老朋友散步" not in str(payload)

    # 公开端免登录可读
    r = client.get(f"/api/v1/card/public/{data['id']}")
    assert r.status_code == 200
    assert r.json()["payload"]["record_count"] == 1


def _family_id(db, username):
    return db.query(User).filter(User.username == username).first().id


def test_public_card_404(client):
    r = client.get("/api/v1/card/public/not-exists")
    assert r.status_code == 404


def test_latest_card_roundtrip(client, db_session):
    elderly = _seed_elderly_with_session(db_session, "13900200005", "李奶奶")
    _, fam_headers = _register_user(client, "13900200006", role="family")
    db_session.add(FamilyLink(elderly_user_id=elderly.id,
                              family_user_id=_family_id(db_session, "13900200006")))
    db_session.commit()

    client.post("/api/v1/card/generate", headers=fam_headers)
    r = client.get("/api/v1/card/latest", headers=fam_headers)
    assert r.status_code == 200
    assert r.json()["card"]["payload"]["elderly_name"] == "李奶奶"


# ========== 匿名公开埋点 ==========
def test_public_events_whitelist_and_anonymous(client, db_session):
    r = client.post("/api/v1/metrics/events/public", json={"events": [
        {"name": "landing_viewed", "properties": {"card_id": "c1"}},
        {"name": "register_from_share", "properties": {"card_id": "c1"}},
        {"name": "hacker_event", "properties": {}},
    ]})
    assert r.status_code == 200
    assert r.json()["accepted"] == 2  # 白名单外丢弃

    from app.models import AnalyticsEvent
    rows = db_session.query(AnalyticsEvent).all()
    assert len(rows) == 2
    for row in rows:
        assert row.user_id is None  # 匿名：无用户态


def test_public_events_no_auth_required(client):
    """不带 Authorization 也应 200（区别于 /metrics/events 的登录态要求）"""
    r = client.post("/api/v1/metrics/events/public", json={"events": [
        {"name": "landing_viewed", "properties": {}},
    ]})
    assert r.status_code == 200
