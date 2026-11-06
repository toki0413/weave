"""交付级安全与边界测试

覆盖本轮生产化整改的关键行为：bcrypt 长度边界、登录防爆破、
限流客户端 IP 取值、可观测端点鉴权、上传体积上限、错误响应脱敏。
"""
from types import SimpleNamespace

import pytest
from starlette.requests import Request


# ---------- 密码长度边界（bcrypt 5.0 拒绝 >72 字节） ----------

def test_register_rejects_password_over_72_bytes(client):
    """中文密码按字符数不超限、按字节超限时必须返回 422 而不是 500"""
    pwd = "测试密码Ab1!" * 5  # 每段 4 汉字(12B)+4 ASCII(4B)=16B，5 段 = 80B > 72B
    assert len(pwd.encode("utf-8")) > 72
    r = client.post("/api/v1/auth/register", json={
        "username": "byte_limit_user", "password": pwd, "role": "elderly",
    })
    assert r.status_code == 422, r.text
    assert "密码过长" in r.text or "字节" in r.text


def test_login_with_overlong_password_returns_401_not_500(client):
    """历史超长密码（旧版本静默截断）登录时不得抛 500"""
    client.post("/api/v1/auth/register", json={
        "username": "len_user", "password": "Test123456!", "role": "elderly",
    })
    r = client.post("/api/v1/auth/login", json={
        "identifier": "len_user", "password": "x" * 200,
    })
    assert r.status_code == 401, r.text


def test_register_rejects_short_password_with_readable_error(client):
    r = client.post("/api/v1/auth/register", json={
        "username": "short_user", "password": "Ab1!", "role": "elderly",
    })
    assert r.status_code == 422


# ---------- 登录防爆破 ----------

def test_login_locked_after_repeated_failures(client, monkeypatch):
    from app.routers import auth as auth_mod

    identifier = "lock_user"
    client.post("/api/v1/auth/register", json={
        "username": identifier, "password": "Test123456!", "role": "elderly",
    })
    key = auth_mod._login_key(identifier)
    auth_mod._clear_login_fail(key)
    try:
        for _ in range(5):
            r = client.post("/api/v1/auth/login", json={
                "identifier": identifier, "password": "WrongPass1!",
            })
            assert r.status_code == 401
        # 第 6 次：账号已锁定，即使密码正确也拒绝
        r = client.post("/api/v1/auth/login", json={
            "identifier": identifier, "password": "Test123456!",
        })
        assert r.status_code == 429
        assert "锁定" in r.json()["detail"]
        # 锁定响应必须给出可等待时长，供客户端退避
        assert r.headers.get("retry-after") == str(15 * 60)
    finally:
        auth_mod._clear_login_fail(key)


def test_login_success_clears_failure_counter(client):
    from app.routers import auth as auth_mod

    identifier = "clear_user"
    client.post("/api/v1/auth/register", json={
        "username": identifier, "password": "Test123456!", "role": "elderly",
    })
    key = auth_mod._login_key(identifier)
    auth_mod._clear_login_fail(key)
    try:
        client.post("/api/v1/auth/login", json={
            "identifier": identifier, "password": "WrongPass1!"})
        assert auth_mod._login_fail_count(key) == 1
        r = client.post("/api/v1/auth/login", json={
            "identifier": identifier, "password": "Test123456!"})
        assert r.status_code == 200
        assert auth_mod._login_fail_count(key) == 0
    finally:
        auth_mod._clear_login_fail(key)


def _fake_request(headers=None, client_host="203.0.113.9"):
    scope = {
        "type": "http", "method": "GET", "path": "/x", "headers": [],
        "client": (client_host, 1234),
    }
    for k, v in (headers or {}).items():
        scope["headers"].append((k.lower().encode(), v.encode()))
    return Request(scope)


def test_client_ip_ignores_xff_by_default(monkeypatch):
    """未声明可信代理时，客户端自带的 XFF 不得影响限流键"""
    from app.rate_limit import _get_client_ip
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "trust_proxy", False)
    req = _fake_request({"x-forwarded-for": "1.2.3.4", "x-real-ip": "1.2.3.4"})
    assert _get_client_ip(req) == "203.0.113.9"


def test_client_ip_uses_real_ip_when_proxy_trusted(monkeypatch):
    from app.rate_limit import _get_client_ip
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "trust_proxy", True)
    req = _fake_request({"x-real-ip": "198.51.100.7"})
    assert _get_client_ip(req) == "198.51.100.7"


def test_client_ip_takes_last_xff_hop_when_proxy_trusted(monkeypatch):
    """XFF 最右值由最近一跳反代写入，客户端伪造的最左值不可采信"""
    from app.rate_limit import _get_client_ip
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "trust_proxy", True)
    req = _fake_request({"x-forwarded-for": "6.6.6.6, 198.51.100.7"})
    assert _get_client_ip(req) == "198.51.100.7"


# ---------- 可观测端点鉴权 ----------

def test_metrics_rejected_for_untrusted_client_without_token(client, monkeypatch):
    """未配置 token 时，非私网来源一律 404（不暴露端点存在性）"""
    from app.main import settings as main_settings
    monkeypatch.setattr(main_settings, "metrics_token", "")
    r = client.get("/metrics")
    assert r.status_code == 404


def test_metrics_requires_bearer_token_when_configured(client, monkeypatch):
    from app.main import settings as main_settings
    monkeypatch.setattr(main_settings, "metrics_token", "s3cret")
    assert client.get("/metrics").status_code == 401
    r = client.get("/metrics", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
    r = client.get("/metrics", headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200
    assert "http_requests_total" in r.text


def test_events_requires_valid_token(client):
    assert client.get("/events").status_code == 401
    assert client.get("/events?token=not-a-jwt").status_code == 401


def test_events_accepts_valid_access_token(client, auth_headers):
    """有效 token 通过鉴权（只校验握手，不消费流，避免测试挂起）"""
    from app.main import _verify_sse_token
    assert _verify_sse_token(auth_headers["token"]) is True
    assert _verify_sse_token("bad.token.value") is False
    assert _verify_sse_token("") is False


def test_metrics_endpoint_label_is_low_cardinality(client, monkeypatch):
    """指标标签必须取路由模板（含挂载前缀），且路径参数被归一化"""
    from app.main import settings as main_settings
    monkeypatch.setattr(main_settings, "metrics_token", "t")
    client.get("/api/v1/auth/me")
    client.get("/api/v1/sessions/3f2a1b4c-0000-1111-2222-333344445555")
    body = client.get(
        "/metrics", headers={"Authorization": "Bearer t"}).text

    assert 'endpoint="/api/v1/auth/me"' in body, "子应用标签丢失挂载前缀"
    assert "{id}" in body, "UUID 路径段未被归一化，标签基数会爆炸"
    assert "unmatched" not in body, "存在未能归一化的路径"


# ---------- 权限提升与横向越权 ----------

def test_self_register_cannot_escalate_role(client):
    """自助注册不得指定 admin / doctor，否则权限体系形同虚设"""
    for role in ("admin", "doctor", "ADMIN"):
        r = client.post("/api/v1/auth/register", json={
            "username": f"esc_{role}", "password": "Test123456!", "role": role,
        })
        assert r.status_code == 400, f"role={role} 竟可自助注册: {r.status_code}"
        assert "后台开通" in r.json()["detail"]


def test_logs_export_denied_for_regular_user(client, auth_headers):
    """应用日志含全站请求记录，普通用户不得导出"""
    r = client.get("/api/v1/backup/logs", headers=auth_headers["headers"])
    assert r.status_code == 403


def test_logs_export_allowed_for_admin(client, auth_headers, db_session):
    from app.models import User
    db_session.query(User).filter(User.username == "13800000000").update(
        {"role": "admin"})
    db_session.commit()
    r = client.get("/api/v1/backup/logs", headers=auth_headers["headers"])
    # 日志目录为空时 404，有日志时 200；两者都不应是 403
    assert r.status_code in (200, 404), r.text


# ---------- 错误响应脱敏 ----------

def test_internal_error_response_has_no_server_path():
    from app.main import _internal_error_response
    req = SimpleNamespace(state=SimpleNamespace(request_id="abc123def456"))
    resp = _internal_error_response(req, RuntimeError("/srv/app/secret.py boom"))
    body = resp.body.decode("utf-8")
    assert "/srv/app" not in body
    assert "log_path" not in body
    assert "abc123def456" in body


# ---------- 上传体积上限 ----------

def test_stt_rejects_oversized_audio(client, auth_headers, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "max_audio_upload_mb", 1)
    big = b"\x00" * (1024 * 1024 + 1024)
    r = client.post(
        "/api/v1/stt/transcribe",
        files={"audio": ("a.webm", big, "audio/webm")},
        headers=auth_headers["headers"],
    )
    assert r.status_code == 413, r.text


def test_backup_import_rejects_oversized_file(client, auth_headers, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "max_backup_import_mb", 1)
    big = b"{\"sessions\": []}" + b" " * (1024 * 1024 + 1024)
    r = client.post(
        "/api/v1/backup/import",
        files={"file": ("backup.json", big, "application/json")},
        headers=auth_headers["headers"],
    )
    assert r.status_code == 413, r.text
