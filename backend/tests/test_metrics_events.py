"""埋点上报与研究漏斗聚合测试（2026-10 工程债修复：此前产品零埋点）

覆盖：
- POST /metrics/events 批量上报（入库、事件名校验、批量上限）
- GET /metrics/research/summary（doctor 权限门控 + 漏斗数字）
- sessions.source 来源归因（白名单外的值回退 manual）
"""
import uuid

from app.models import AnalyticsEvent, Notification, Session as DBSession, User

# 与 test_notification.py 一致的注册辅助
def _register_user(client, phone, password="Test123456!", role="elderly", name=None):
    body = {"phone": phone, "password": password, "role": role}
    if name:
        body["name"] = name
    r = client.post("/api/v1/auth/register", json=body)
    assert r.status_code == 200, f"注册失败: {r.text}"
    token = r.json()["access_token"]
    return r.json(), {"Authorization": f"Bearer {token}"}


# ========== 事件上报 ==========
def test_batch_upload_stores_events(client, db_session):
    _, headers = _register_user(client, "13900100001", name="老人A")

    r = client.post("/api/v1/metrics/events", headers=headers, json={
        "events": [
            {"name": "daily_prompt_exposed", "properties": {"topic": "food"}, "client_ts": "2026-10-20T08:00:00Z"},
            {"name": "daily_prompt_filled", "properties": {}, "client_ts": None},
        ],
    })
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] == 2

    rows = db_session.query(AnalyticsEvent).all()
    assert len(rows) == 2
    user = db_session.query(User).filter(User.username == "13900100001").first()
    assert {row.event_name for row in rows} == {"daily_prompt_exposed", "daily_prompt_filled"}
    for row in rows:
        assert row.user_id == user.id  # 登录态归因


def test_event_name_pattern_rejected(client):
    """事件名必须是小写字母/数字/下划线/点，防止脏数据进漏斗"""
    _, headers = _register_user(client, "13900100002")
    r = client.post("/api/v1/metrics/events", headers=headers, json={
        "events": [{"name": "Bad Event!", "properties": {}}],
    })
    assert r.status_code == 422


def test_batch_over_50_rejected(client):
    _, headers = _register_user(client, "13900100003")
    events = [{"name": "daily_prompt_exposed", "properties": {}} for _ in range(51)]
    r = client.post("/api/v1/metrics/events", headers=headers, json={"events": events})
    assert r.status_code == 422


def test_oversized_properties_truncated(client, db_session):
    """属性超过 1KB 时丢弃属性只留事件名（隐私与体积红线）"""
    _, headers = _register_user(client, "13900100004")
    big = {"payload": "x" * 2048}
    r = client.post("/api/v1/metrics/events", headers=headers, json={
        "events": [{"name": "daily_prompt_exposed", "properties": big}],
    })
    assert r.status_code == 200
    row = db_session.query(AnalyticsEvent).first()
    assert row.properties == {"_truncated": True}


# ========== 研究漏斗聚合 ==========
def test_research_summary_requires_doctor(client):
    _, elderly_headers = _register_user(client, "13900100005", role="elderly")
    r = client.get("/api/v1/metrics/research/summary", headers=elderly_headers)
    assert r.status_code == 403


def test_research_summary_requires_doctor_family(client):
    _, fam_headers = _register_user(client, "13900100006", role="family")
    r = client.get("/api/v1/metrics/research/summary", headers=fam_headers)
    assert r.status_code == 403


def test_research_summary_funnel_numbers(client, db_session):
    doctor, doctor_headers = _register_user(client, "13900100007", role="doctor", name="研究医生")
    _, elderly_headers = _register_user(client, "13900100008", role="elderly", name="老人B")

    # 日课漏斗前两环：曝光 3 次、填入 1 次
    events = [{"name": "daily_prompt_exposed", "properties": {}} for _ in range(3)]
    events.append({"name": "daily_prompt_filled", "properties": {}})
    r = client.post("/api/v1/metrics/events", headers=elderly_headers, json={"events": events})
    assert r.status_code == 200

    # 第三环：来源归因会话（提交）。另一条 manual 会话不计入
    for source in ("daily_prompt", None):
        body = {"day_number": 1, "narrative_input": {"text": "今天在公园散步，心情不错"}}
        if source:
            body["source"] = source
        r = client.post("/api/v1/session/", headers=elderly_headers, json=body)
        assert r.status_code == 200, r.text

    # 告警漏斗：2 条 anomaly 告警，1 条标记 false_alarm
    user = db_session.query(User).filter(User.username == "13900100008").first()
    db_session.add_all([
        Notification(user_id=user.id, type="anomaly", title="告警一",
                     severity="warning", resolution_status="false_alarm"),
        Notification(user_id=user.id, type="anomaly", title="告警二", severity="info"),
    ])
    db_session.commit()

    r = client.get("/api/v1/metrics/research/summary?days=30", headers=doctor_headers)
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["daily_prompt"]["exposed"] == 3
    assert data["daily_prompt"]["filled"] == 1
    assert data["daily_prompt"]["submitted"] == 1  # 只算 source=daily_prompt 的会话
    assert data["daily_prompt"]["fill_rate"] == 0.3333
    assert data["daily_prompt"]["submit_rate"] == 1.0

    assert data["alerts"]["created"] == 2
    assert data["alerts"]["false_alarm"] == 1
    assert data["alerts"]["false_alarm_rate"] == 0.5
    # resolved = 非 pending 的 1 条（false_alarm 已视为处理完毕）
    assert data["alerts"]["resolved"] == 1


def test_research_summary_empty_window(client):
    """无任何数据时漏斗应为零值而非报错"""
    _, doctor_headers = _register_user(client, "13900100009", role="doctor")
    r = client.get("/api/v1/metrics/research/summary", headers=doctor_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["daily_prompt"]["exposed"] == 0
    assert data["daily_prompt"]["submitted"] == 0
    assert data["alerts"]["created"] == 0


# ========== 会话来源归因 ==========
def test_session_source_whitelist(client, db_session):
    """source 白名单外的值回退 manual"""
    _, headers = _register_user(client, "13900100010", role="elderly", name="老人C")

    r = client.post("/api/v1/session/", headers=headers, json={
        "day_number": 1,
        "narrative_input": {"text": "今天吃了饺子"},
        "source": "daily_prompt",
    })
    assert r.status_code == 200
    r = client.post("/api/v1/session/", headers=headers, json={
        "day_number": 2,
        "narrative_input": {"text": "今天喝了粥"},
        "source": "javascript:alert(1)",
    })
    assert r.status_code == 200

    sessions = db_session.query(DBSession).order_by(DBSession.day_number).all()
    assert sessions[0].source == "daily_prompt"
    assert sessions[1].source == "manual"  # 非法值回退
