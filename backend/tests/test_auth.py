"""认证相关接口测试"""


def test_register_success(client):
    """正常注册应返回 token"""
    r = client.post("/api/v1/auth/register", json={
        "phone": "13900000001",
        "password": "Password123!",
        "name": "新用户",
    })
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_register_duplicate(client):
    """同一手机号二次注册应被拒绝"""
    payload = {"phone": "13900000002", "password": "Password123!"}
    r1 = client.post("/api/v1/auth/register", json=payload)
    assert r1.status_code == 200

    r2 = client.post("/api/v1/auth/register", json=payload)
    assert r2.status_code == 400
    assert "already registered" in r2.json()["detail"].lower()


def test_register_short_password(client):
    """密码短于 6 位应被 Pydantic 拦截"""
    r = client.post("/api/v1/auth/register", json={
        "phone": "13900000003",
        "password": "123",
    })
    assert r.status_code == 422


def test_login_success(client):
    """注册后用相同密码登录应成功"""
    client.post("/api/v1/auth/register", json={
        "phone": "13900000004",
        "password": "Password123!",
    })
    r = client.post("/api/v1/auth/login", json={
        "phone": "13900000004",
        "password": "Password123!",
    })
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_wrong_password(client):
    """密码错误应返回 401"""
    client.post("/api/v1/auth/register", json={
        "phone": "13900000005",
        "password": "Password123!",
    })
    r = client.post("/api/v1/auth/login", json={
        "phone": "13900000005",
        "password": "wrongpassword",
    })
    assert r.status_code == 401


def test_me_without_token(client):
    """不带 token 访问 /auth/me 应返回 401"""
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_me_with_token(client, auth_headers):
    """带合法 token 访问 /auth/me 应返回当前用户信息"""
    r = client.get("/api/v1/auth/me", headers=auth_headers["headers"])
    assert r.status_code == 200
    data = r.json()
    assert data["phone"] == "13800000000"
    assert data["name"] == "测试用户"


def test_register_returns_recovery_code(client):
    """注册接口应返回恢复码"""
    r = client.post("/api/v1/auth/register", json={
        "phone": "13900000006",
        "password": "Password123!",
        "name": "恢复码用户",
    })
    assert r.status_code == 200
    data = r.json()
    assert "recovery_code" in data
    assert len(data["recovery_code"]) >= 20


def test_recovery_and_change_password(client):
    """用恢复码重置密码后，新密码可登录；修改密码后旧密码失效"""
    phone = "13900000007"
    old_password = "Password123!"
    r = client.post("/api/v1/auth/register", json={
        "phone": phone,
        "password": old_password,
        "name": "测试恢复",
    })
    assert r.status_code == 200
    recovery_code = r.json()["recovery_code"]

    # 用错误恢复码应失败
    r = client.post("/api/v1/auth/recovery", json={
        "phone": phone,
        "recovery_code": "wrong-code",
        "new_password": "NewPass123!",
    })
    assert r.status_code == 401

    # 用正确恢复码重置密码
    r = client.post("/api/v1/auth/recovery", json={
        "phone": phone,
        "recovery_code": recovery_code,
        "new_password": "NewPass123!",
    })
    assert r.status_code == 200
    assert "recovery_code" in r.json()
    new_recovery_code = r.json()["recovery_code"]

    # 新密码可登录
    r = client.post("/api/v1/auth/login", json={"phone": phone, "password": "NewPass123!"})
    assert r.status_code == 200
    assert "access_token" in r.json()

    # 旧密码不可登录
    r = client.post("/api/v1/auth/login", json={"phone": phone, "password": old_password})
    assert r.status_code == 401

    # 修改密码
    token = client.post("/api/v1/auth/login", json={"phone": phone, "password": "NewPass123!"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/v1/auth/change-password", json={
        "old_password": "NewPass123!",
        "new_password": "AnotherPass123!",
    }, headers=headers)
    assert r.status_code == 200

    # 旧密码（newpassword123）失效
    r = client.post("/api/v1/auth/login", json={"phone": phone, "password": "NewPass123!"})
    assert r.status_code == 401

    # 新密码可登录
    r = client.post("/api/v1/auth/login", json={"phone": phone, "password": "AnotherPass123!"})
    assert r.status_code == 200

    # 原恢复码（第一次生成的）应已失效
    r = client.post("/api/v1/auth/recovery", json={
        "phone": phone,
        "recovery_code": recovery_code,
        "new_password": "ShouldFail123!",
    })
    assert r.status_code == 401

    # 新的恢复码可用
    r = client.post("/api/v1/auth/recovery", json={
        "phone": phone,
        "recovery_code": new_recovery_code,
        "new_password": "FinalPass123!",
    })
    assert r.status_code == 200
