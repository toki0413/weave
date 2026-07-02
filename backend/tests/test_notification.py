"""家属端通知相关接口测试"""
import uuid
from datetime import datetime, timedelta, timezone

from app.models import Notification, FamilyLink, User, Session as DBSession
from app.services.notification_service import (
    create_anomaly_notification,
    create_decline_notification,
    create_scale_reminder,
)


# ========== 辅助函数 ==========
def _register_user(client, phone, password="Test123456!", role="elderly", name=None):
    """注册用户并返回 (user_dict, headers)"""
    body = {"phone": phone, "password": password, "role": role}
    if name:
        body["name"] = name
    r = client.post("/api/v1/auth/register", json=body)
    assert r.status_code == 200, f"注册失败: {r.text}"
    token = r.json()["access_token"]
    return r.json(), {"Authorization": f"Bearer {token}"}


def _create_anomaly_session(client, headers, text="今天去医院打太极，然后回家做饭", day=1):
    """创建一个会产生异常的会话"""
    return client.post(
        "/api/v1/session/",
        headers=headers,
        json={
            "day_number": day,
            "narrative_input": {"text": text},
        },
    )


# ========== 通知列表 ==========
def test_list_notifications_empty(client, auth_headers):
    """新用户通知列表应为空"""
    r = client.get("/api/v1/notification/", headers=auth_headers["headers"])
    assert r.status_code == 200
    assert r.json() == []


def test_list_notifications_requires_auth(client):
    """未认证访问应返回 401"""
    r = client.get("/api/v1/notification/")
    assert r.status_code == 401


def test_unread_count_zero(client, auth_headers):
    """新用户未读数应为 0"""
    r = client.get("/api/v1/notification/unread-count", headers=auth_headers["headers"])
    assert r.status_code == 200
    assert r.json()["unread_count"] == 0


# ========== 标记已读 ==========
def test_mark_read_not_found(client, auth_headers):
    """标记不存在的通知应返回 404"""
    r = client.put("/api/v1/notification/nonexistent-id/read", headers=auth_headers["headers"])
    assert r.status_code == 404


def test_mark_all_read_empty(client, auth_headers):
    """没有通知时全部已读应正常返回"""
    r = client.put("/api/v1/notification/read-all", headers=auth_headers["headers"])
    assert r.status_code == 200
    assert r.json()["updated"] == 0


# ========== 家属-老人绑定 ==========
def test_link_family_member_by_phone(client):
    """家属通过手机号绑定老人"""
    # 先注册一个老人
    _register_user(client, "13900000001", role="elderly", name="张大爷")
    # 再注册一个家属
    _, fam_headers = _register_user(client, "13900000002", role="family", name="张小华")

    r = client.post(
        "/api/v1/notification/family-link",
        headers=fam_headers,
        json={"elderly_username": "13900000001", "relation": "子女"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["elderly_phone"] == "13900000001"
    assert data["elderly_name"] == "张大爷"
    assert data["relation"] == "子女"


def test_link_family_member_by_name(client):
    """家属通过姓名绑定老人"""
    _register_user(client, "13900000003", role="elderly", name="李奶奶")
    _, fam_headers = _register_user(client, "13900000004", role="family", name="李明")

    r = client.post(
        "/api/v1/notification/family-link",
        headers=fam_headers,
        json={"elderly_username": "李奶奶"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["elderly_name"] == "李奶奶"


def test_link_family_member_not_found(client, auth_headers):
    """绑定不存在的老人应返回 404"""
    r = client.post(
        "/api/v1/notification/family-link",
        headers=auth_headers["headers"],
        json={"elderly_username": "不存在的用户"},
    )
    assert r.status_code == 404


def test_link_family_member_self(client, auth_headers):
    """不能绑定自己为老人"""
    r = client.post(
        "/api/v1/notification/family-link",
        headers=auth_headers["headers"],
        json={"elderly_username": "13800000000"},
    )
    assert r.status_code == 400


def test_link_family_member_duplicate(client):
    """重复绑定返回原记录，不报错"""
    _register_user(client, "13900000005", role="elderly", name="王大爷")
    _, fam_headers = _register_user(client, "13900000006", role="family", name="王小")

    # 第一次绑定
    r1 = client.post(
        "/api/v1/notification/family-link",
        headers=fam_headers,
        json={"elderly_username": "13900000005", "relation": "子女"},
    )
    assert r1.status_code == 200

    # 重复绑定
    r2 = client.post(
        "/api/v1/notification/family-link",
        headers=fam_headers,
        json={"elderly_username": "13900000005", "relation": "子女"},
    )
    assert r2.status_code == 200
    assert r1.json()["link_id"] == r2.json()["link_id"]


def test_list_family_members(client):
    """家属查看自己绑定的老人列表"""
    _register_user(client, "13900000007", role="elderly", name="老人A")
    _register_user(client, "13900000008", role="elderly", name="老人B")
    _, fam_headers = _register_user(client, "13900000009", role="family", name="家属C")

    # 绑定两个老人
    for phone in ["13900000007", "13900000008"]:
        r = client.post(
            "/api/v1/notification/family-link",
            headers=fam_headers,
            json={"elderly_username": phone, "relation": "子女"},
        )
        assert r.status_code == 200

    r = client.get("/api/v1/notification/family-members", headers=fam_headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    names = [m["elderly_name"] for m in data]
    assert "老人A" in names
    assert "老人B" in names


def test_list_family_members_empty(client, auth_headers):
    """没有绑定任何老人时返回空列表"""
    r = client.get("/api/v1/notification/family-members", headers=auth_headers["headers"])
    assert r.status_code == 200
    assert r.json() == []


# ========== 通知服务直接测试 ==========
def test_create_anomaly_notification_no_family(db_session):
    """没有绑定家属时，创建异常通知应返回 0"""
    user = User(id=str(uuid.uuid4()), username="13900000010", hashed_password="x", role="elderly")
    db_session.add(user)
    db_session.commit()

    anomalies = [{"event": "打太极", "severity": "warning", "type": "event-place-mismatch"}]
    count = create_anomaly_notification(user.id, anomalies, db_session)
    assert count == 0


def test_create_anomaly_notification_with_family(db_session):
    """有绑定家属时，异常通知应写入家属账号"""
    elderly = User(id=str(uuid.uuid4()), username="13900000011", hashed_password="x", role="elderly", name="老人")
    family = User(id=str(uuid.uuid4()), username="13900000012", hashed_password="x", role="family", name="家属")
    db_session.add_all([elderly, family])
    db_session.commit()

    link = FamilyLink(elderly_user_id=elderly.id, family_user_id=family.id, relation="子女")
    db_session.add(link)
    db_session.commit()

    anomalies = [{"event": "打太极", "severity": "danger", "type": "event-place-mismatch"}]
    count = create_anomaly_notification(elderly.id, anomalies, db_session)
    assert count == 1

    # 家属应该能看到这条通知
    notifs = db_session.query(Notification).filter(Notification.user_id == family.id).all()
    assert len(notifs) == 1
    assert notifs[0].type == "anomaly"
    assert notifs[0].severity == "danger"
    assert notifs[0].is_read is False


def test_create_anomaly_notification_empty(db_session):
    """空异常列表不发通知"""
    elderly = User(id=str(uuid.uuid4()), username="13900000013", hashed_password="x", role="elderly")
    family = User(id=str(uuid.uuid4()), username="13900000014", hashed_password="x", role="family")
    link = FamilyLink(elderly_user_id=elderly.id, family_user_id=family.id)
    db_session.add_all([elderly, family, link])
    db_session.commit()

    count = create_anomaly_notification(elderly.id, [], db_session)
    assert count == 0


def test_create_decline_notification_normal_skip(db_session):
    """衰退分数正常时不发通知"""
    elderly = User(id=str(uuid.uuid4()), username="13900000015", hashed_password="x", role="elderly")
    family = User(id=str(uuid.uuid4()), username="13900000016", hashed_password="x", role="family")
    link = FamilyLink(elderly_user_id=elderly.id, family_user_id=family.id)
    db_session.add_all([elderly, family, link])
    db_session.commit()

    decline_data = {"decline_score": 10, "level": "正常", "window_days": 7}
    count = create_decline_notification(elderly.id, decline_data, db_session)
    assert count == 0


def test_create_decline_notification_warning(db_session):
    """衰退分数关注级别时发 warning 通知"""
    elderly = User(id=str(uuid.uuid4()), username="13900000017", hashed_password="x", role="elderly")
    family = User(id=str(uuid.uuid4()), username="13900000018", hashed_password="x", role="family")
    link = FamilyLink(elderly_user_id=elderly.id, family_user_id=family.id)
    db_session.add_all([elderly, family, link])
    db_session.commit()

    decline_data = {
        "decline_score": 35,
        "level": "关注",
        "window_days": 7,
        "forgotten_entities": [{"entity": "老张", "previous_count": 3, "days_absent": 7}],
    }
    count = create_decline_notification(elderly.id, decline_data, db_session)
    assert count == 1

    notif = db_session.query(Notification).filter(Notification.user_id == family.id).first()
    assert notif.type == "decline"
    assert notif.severity == "warning"


def test_create_decline_notification_danger(db_session):
    """衰退分数警告级别时发 danger 通知"""
    elderly = User(id=str(uuid.uuid4()), username="13900000019", hashed_password="x", role="elderly")
    family = User(id=str(uuid.uuid4()), username="13900000020", hashed_password="x", role="family")
    link = FamilyLink(elderly_user_id=elderly.id, family_user_id=family.id)
    db_session.add_all([elderly, family, link])
    db_session.commit()

    decline_data = {"decline_score": 60, "level": "警告", "window_days": 7}
    count = create_decline_notification(elderly.id, decline_data, db_session)
    assert count == 1

    notif = db_session.query(Notification).filter(Notification.user_id == family.id).first()
    assert notif.severity == "danger"


def test_create_scale_reminder_no_history(db_session):
    """从未做过量表时也提醒"""
    elderly = User(id=str(uuid.uuid4()), username="13900000021", hashed_password="x", role="elderly")
    family = User(id=str(uuid.uuid4()), username="13900000022", hashed_password="x", role="family")
    link = FamilyLink(elderly_user_id=elderly.id, family_user_id=family.id)
    db_session.add_all([elderly, family, link])
    db_session.commit()

    count = create_scale_reminder(elderly.id, db_session)
    assert count == 1

    notif = db_session.query(Notification).filter(Notification.user_id == family.id).first()
    assert notif.type == "scale_reminder"
    assert notif.severity == "info"


def test_create_scale_reminder_recent_skip(db_session):
    """刚做过量表不久不提醒"""
    from app.models import ScaleRecord
    elderly = User(id=str(uuid.uuid4()), username="13900000023", hashed_password="x", role="elderly")
    family = User(id=str(uuid.uuid4()), username="13900000024", hashed_password="x", role="family")
    link = FamilyLink(elderly_user_id=elderly.id, family_user_id=family.id)
    db_session.add_all([elderly, family, link])

    # 最近做过量表
    record = ScaleRecord(
        user_id=elderly.id,
        scale_type="mmse",
        answers=[],
        total_score=28,
        interpretation="正常",
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    db_session.add(record)
    db_session.commit()

    count = create_scale_reminder(elderly.id, db_session)
    assert count == 0


# ========== 通知读写完整流程 ==========
def test_notification_full_flow(client, db_session):
    """完整流程：绑定 → 收到通知 → 列表 → 标记已读 → 未读数清零"""
    # 注册老人和家属
    _register_user(client, "13900000025", role="elderly", name="测试老人")
    _, fam_headers = _register_user(client, "13900000026", role="family", name="测试家属")

    # 家属绑定老人
    r = client.post(
        "/api/v1/notification/family-link",
        headers=fam_headers,
        json={"elderly_username": "13900000025", "relation": "子女"},
    )
    assert r.status_code == 200

    # 直接通过服务层给家属写一条通知
    elderly = db_session.query(User).filter(User.phone == "13900000025").first()
    family = db_session.query(User).filter(User.phone == "13900000026").first()
    anomalies = [{"event": "打太极", "severity": "warning", "type": "event-place-mismatch"}]
    create_anomaly_notification(elderly.id, anomalies, db_session)

    # 家属查看通知列表
    r = client.get("/api/v1/notification/", headers=fam_headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["type"] == "anomaly"
    assert data[0]["is_read"] is False

    # 未读数应为 1
    r = client.get("/api/v1/notification/unread-count", headers=fam_headers)
    assert r.json()["unread_count"] == 1

    # 标记已读
    notif_id = data[0]["id"]
    r = client.put(f"/api/v1/notification/{notif_id}/read", headers=fam_headers)
    assert r.status_code == 200

    # 未读数应为 0
    r = client.get("/api/v1/notification/unread-count", headers=fam_headers)
    assert r.json()["unread_count"] == 0

    # unread=true 过滤应返回空
    r = client.get("/api/v1/notification/?unread=true", headers=fam_headers)
    assert r.json() == []


def test_mark_all_read_flow(client, db_session):
    """全部已读：多条未读一次性清掉"""
    _register_user(client, "13900000027", role="elderly", name="老人")
    _, fam_headers = _register_user(client, "13900000028", role="family", name="家属")
    client.post(
        "/api/v1/notification/family-link",
        headers=fam_headers,
        json={"elderly_username": "13900000027"},
    )

    elderly = db_session.query(User).filter(User.phone == "13900000027").first()
    # 写 3 条通知
    for i in range(3):
        anomalies = [{"event": f"事件{i}", "severity": "warning"}]
        create_anomaly_notification(elderly.id, anomalies, db_session)

    # 确认 3 条未读
    r = client.get("/api/v1/notification/unread-count", headers=fam_headers)
    assert r.json()["unread_count"] == 3

    # 全部已读
    r = client.put("/api/v1/notification/read-all", headers=fam_headers)
    assert r.status_code == 200
    assert r.json()["updated"] == 3

    # 未读应为 0
    r = client.get("/api/v1/notification/unread-count", headers=fam_headers)
    assert r.json()["unread_count"] == 0


# ========== 会话创建触发通知集成测试 ==========
def test_session_creates_notification_for_family(client, db_session):
    """老人创建会话产生异常时，绑定的家属应自动收到通知"""
    # 注册老人（注册即缓存加密密钥）
    _register_user(client, "13900000029", role="elderly", name="老人X")
    _, fam_headers = _register_user(client, "13900000030", role="family", name="家属Y")

    # 家属绑定老人
    client.post(
        "/api/v1/notification/family-link",
        headers=fam_headers,
        json={"elderly_username": "13900000029", "relation": "子女"},
    )

    # 老人登录并创建会话（"去医院打太极"会触发事件-地点不匹配异常）
    r = client.post("/api/v1/auth/login", json={"phone": "13900000029", "password": "Test123456!"})
    elderly_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post(
        "/api/v1/session/",
        headers=elderly_headers,
        json={
            "day_number": 1,
            "narrative_input": {"text": "今天去医院打太极，然后回家做饭"},
        },
    )
    assert r.status_code == 200, r.text
    # 确认会话确实产生了异常
    assert len(r.json()["anomalies"]) > 0

    # 家属应该能看到通知
    r = client.get("/api/v1/notification/", headers=fam_headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    assert data[0]["type"] == "anomaly"


def test_session_no_anomaly_no_notification(client):
    """老人创建正常会话（无异常）时，家属不应收到通知"""
    _register_user(client, "13900000031", role="elderly", name="正常老人")
    _, fam_headers = _register_user(client, "13900000032", role="family", name="正常家属")
    client.post(
        "/api/v1/notification/family-link",
        headers=fam_headers,
        json={"elderly_username": "13900000031"},
    )

    r = client.post("/api/v1/auth/login", json={"phone": "13900000031", "password": "Test123456!"})
    elderly_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    # "聊天"不在语义规则里，不会触发事件-地点异常
    r = client.post(
        "/api/v1/session/",
        headers=elderly_headers,
        json={
            "day_number": 1,
            "narrative_input": {"text": "今天和老伴在公园聊天，很开心"},
        },
    )
    assert r.status_code == 200
    # 确认没有产生异常
    assert r.json()["anomalies"] == []

    # 家属不应有通知
    r = client.get("/api/v1/notification/", headers=fam_headers)
    assert r.json() == []


def test_notification_isolated_between_users(client, db_session):
    """通知按用户隔离：A 家属看不到 B 家属的通知"""
    _register_user(client, "13900000033", role="elderly", name="老人C")
    _, fam_a_headers = _register_user(client, "13900000034", role="family", name="家属A")
    _, fam_b_headers = _register_user(client, "13900000035", role="family", name="家属B")

    # 只有家属A绑定老人
    client.post(
        "/api/v1/notification/family-link",
        headers=fam_a_headers,
        json={"elderly_username": "13900000033"},
    )

    # 老人创建异常会话
    r = client.post("/api/v1/auth/login", json={"phone": "13900000033", "password": "Test123456!"})
    elderly_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    client.post(
        "/api/v1/session/",
        headers=elderly_headers,
        json={
            "day_number": 1,
            "narrative_input": {"text": "今天去医院打太极"},
        },
    )

    # 家属A有通知
    r = client.get("/api/v1/notification/", headers=fam_a_headers)
    assert len(r.json()) >= 1

    # 家属B没有通知
    r = client.get("/api/v1/notification/", headers=fam_b_headers)
    assert r.json() == []
