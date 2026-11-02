"""告警出站触达通道（gap 审计 G1）测试

覆盖：severity 门槛、SMTP/webhook 发送协议、逐收件人失败隔离、
notification_service 的出站接线（warning 及以上、频控命中的不出站）。
"""
import base64
from types import SimpleNamespace

import pytest

from app.services import alert_channels
from app.services.notification_service import create_emotion_notification
from app.models import User, FamilyLink


@pytest.fixture
def settings_override(monkeypatch):
    """直接改 lru_cache 的 Settings 实例属性，monkeypatch 负责还原"""
    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "alert_outbound_min_severity", "warning")
    monkeypatch.setattr(s, "smtp_host", "smtp.test.local")
    monkeypatch.setattr(s, "smtp_port", 465)
    monkeypatch.setattr(s, "smtp_user", "bot@test.local")
    monkeypatch.setattr(s, "smtp_password", "secret")
    monkeypatch.setattr(s, "smtp_from", "bot@test.local")
    monkeypatch.setattr(s, "smtp_use_ssl", True)
    monkeypatch.setattr(s, "alert_webhook_url", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=x")
    return s


# ---------- severity 门槛 ----------

def test_dispatch_skips_info(settings_override, db_session):
    called = {"n": 0}

    def _fake(*a, **k):
        called["n"] += 1
        return True

    monkey = pytest.MonkeyPatch()
    monkey.setattr(alert_channels, "_send_webhook", _fake)
    try:
        result = alert_channels.dispatch_alert(
            db_session, [], "标题", "内容", "info")
    finally:
        monkey.undo()
    assert result == {"email": 0, "webhook": 0}
    assert called["n"] == 0


# ---------- webhook 协议 ----------

def test_send_webhook_wecom_protocol(monkeypatch):
    captured = {}

    class _Resp:
        def __init__(self, status, body):
            self.status_code = status
            self._body = body

        def json(self):
            if self._body is None:
                raise ValueError("not json")
            return self._body

    def _fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _Resp(200, {"errcode": 0})

    monkeypatch.setattr(alert_channels.httpx, "post", _fake_post)
    assert alert_channels._send_webhook("hello", "https://wecom/x") is True
    assert captured["json"]["msgtype"] == "text"
    assert captured["json"]["text"]["content"] == "hello"

    monkeypatch.setattr(
        alert_channels.httpx, "post",
        lambda url, json=None, timeout=None: _Resp(200, {"errcode": 94000}))
    # 企业微信 HTTP 200 但业务失败（关键词不匹配等）不算送达
    assert alert_channels._send_webhook("hello", "https://wecom/x") is False

    monkeypatch.setattr(
        alert_channels.httpx, "post",
        lambda url, json=None, timeout=None: _Resp(500, None))
    assert alert_channels._send_webhook("hello", "https://wecom/x") is False

    # 通用 webhook：200 非 JSON 也算送达
    monkeypatch.setattr(
        alert_channels.httpx, "post",
        lambda url, json=None, timeout=None: _Resp(200, None))
    assert alert_channels._send_webhook("hello", "https://generic/x") is True


# ---------- SMTP 协议 ----------

def test_send_email_smtp_protocol(monkeypatch):
    captured = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            captured["host"] = host
            captured["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, user, pwd):
            captured["user"] = user

        def sendmail(self, sender, to, msg):
            captured["sender"] = sender
            captured["to"] = to
            captured["msg"] = msg

        def close(self):
            pass

    monkeypatch.setattr(alert_channels.smtplib, "SMTP_SSL", _FakeSMTP)
    s = SimpleNamespace(
        smtp_host="smtp.test.local", smtp_port=465, smtp_user="bot@test.local",
        smtp_password="secret", smtp_from="", smtp_use_ssl=True)
    ok = alert_channels._send_email("a@test.local", "主题", "正文", s)
    assert ok is True
    assert captured["to"] == ["a@test.local"]

    # MIME 报文里主题/正文都是编码后的，用标准解析器还原后断言
    import email as _email
    from email.header import decode_header, make_header
    m = _email.message_from_string(captured["msg"])
    assert m["To"] == "a@test.local"
    assert str(make_header(decode_header(m["Subject"]))) == "主题"
    assert m.get_payload(decode=True).decode("utf-8") == "正文"


# ---------- 派发编排 ----------

def _mk_user(db, username, notify_email=None):
    u = User(username=username, hashed_password="x", role="family",
             name=username, notify_email=notify_email)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_dispatch_email_per_user(settings_override, db_session, monkeypatch):
    u1 = _mk_user(db_session, "fam1", notify_email="a@test.local")
    u2 = _mk_user(db_session, "fam2", notify_email=None)  # 没填邮箱，跳过
    sent = []

    monkeypatch.setattr(
        alert_channels, "_send_email",
        lambda to, subject, body, s: sent.append(to) or True)

    result = alert_channels.dispatch_alert(
        db_session, [u1.id, u2.id], "衰退提醒", "内容", "warning")
    assert result["email"] == 1
    assert sent == ["a@test.local"]


def test_dispatch_email_failure_isolated(settings_override, db_session, monkeypatch):
    u1 = _mk_user(db_session, "fam1", notify_email="a@test.local")
    u2 = _mk_user(db_session, "fam2", notify_email="b@test.local")

    def _flaky(to, subject, body, s):
        if to == "a@test.local":
            raise RuntimeError("smtp down")
        return True

    monkeypatch.setattr(alert_channels, "_send_email", _flaky)
    monkeypatch.setattr(
        alert_channels, "_send_webhook",
        lambda text, url: True)

    result = alert_channels.dispatch_alert(
        db_session, [u1.id, u2.id], "标题", "内容", "danger")
    # 单人邮件失败不拖垮其余通道
    assert result == {"email": 1, "webhook": 1}


# ---------- notification_service 接线 ----------

def test_create_emotion_notification_triggers_outbound(
        settings_override, db_session, monkeypatch):
    elderly = _mk_user(db_session, "elderly1")
    family = _mk_user(db_session, "fam3", notify_email="fam3@test.local")
    db_session.add(FamilyLink(
        family_user_id=family.id, elderly_user_id=elderly.id, is_active=True))
    db_session.commit()

    captured = {}

    def _fake_dispatch(db, family_user_ids, title, content, severity):
        captured["ids"] = list(family_user_ids)
        captured["severity"] = severity
        return {"email": 1, "webhook": 0}

    monkeypatch.setattr(alert_channels, "dispatch_alert", _fake_dispatch)

    written = create_emotion_notification(elderly.id, "11-01", "11-03", db_session)
    assert written == 1
    assert captured["ids"] == [family.id]
    assert captured["severity"] == "warning"
