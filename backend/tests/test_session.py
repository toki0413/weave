"""会话相关接口测试"""
from app.services import key_manager
from app.services.crypto import derive_key, encrypt


def _create_session(client, headers, text="今天和老伴去公园散步", day=1):
    """辅助：创建一个会话"""
    return client.post(
        "/api/v1/session/",
        headers=headers,
        json={
            "day_number": day,
            "narrative_input": {"text": text},
        },
    )


def test_create_session(client, auth_headers):
    """创建会话应返回完整 SessionOut"""
    r = _create_session(client, auth_headers["headers"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["narrative"] == "今天和老伴去公园散步"
    assert "graph" in data
    assert "metrics" in data
    assert isinstance(data["graph"], dict)
    assert "nodes" in data["graph"]


def test_list_sessions(client, auth_headers):
    """列出会话应返回当前用户全部会话"""
    for i in range(3):
        r = _create_session(client, auth_headers["headers"], day=i + 1)
        assert r.status_code == 200
    r = client.get("/api/v1/session/", headers=auth_headers["headers"])
    assert r.status_code == 200
    assert len(r.json()) == 3


def test_get_session(client, auth_headers):
    """根据 id 获取单个会话"""
    r = _create_session(client, auth_headers["headers"])
    sid = r.json()["id"]

    r = client.get(f"/api/v1/session/{sid}", headers=auth_headers["headers"])
    assert r.status_code == 200
    assert r.json()["id"] == sid


def test_get_session_not_found(client, auth_headers):
    """不存在的会话 id 应返回 404"""
    r = client.get("/api/v1/session/nonexistent-id", headers=auth_headers["headers"])
    assert r.status_code == 404


def test_health_trend(client, auth_headers):
    """健康趋势应返回按时间正序的列表"""
    for i in range(3):
        _create_session(client, auth_headers["headers"], day=i + 1)
    r = client.get("/api/v1/session/trend/health", headers=auth_headers["headers"])
    assert r.status_code == 200
    data = r.json()
    assert "trend" in data
    assert len(data["trend"]) == 3
    # 列表按 day 升序
    days = [item["day"] for item in data["trend"]]
    assert days == sorted(days)


def test_session_requires_key(client, auth_headers):
    """内存中无加密密钥时，应返回 401"""
    r = _create_session(client, auth_headers["headers"])
    assert r.status_code == 200
    sid = r.json()["id"]

    key_manager.clear_all()
    r = client.get(f"/api/v1/session/{sid}", headers=auth_headers["headers"])
    assert r.status_code == 401


def test_session_decrypt_legacy_data(client, auth_headers, db_session):
    """旧数据用 KEK 直接加密时，应能兼容解密"""
    from app.models import Session as DBSession, User

    text_old = "旧格式加密的数据"
    r = _create_session(client, auth_headers["headers"], text=text_old)
    assert r.status_code == 200
    sid = r.json()["id"]

    # 拿到用户 KEK，模拟旧数据：用 KEK 直接加密 narrative
    user = db_session.query(User).filter(User.phone == "13800000000").first()
    kek = key_manager.get_user_kek(str(user.id))
    encrypted_with_kek = encrypt(text_old, kek)

    db_session.query(DBSession).filter(DBSession.id == sid).update({
        "narrative": encrypted_with_kek,
        "is_encrypted": True,
    })
    db_session.commit()

    # 重新请求应能解密返回明文
    r = client.get(f"/api/v1/session/{sid}", headers=auth_headers["headers"])
    assert r.status_code == 200
    assert r.json()["narrative"] == text_old
