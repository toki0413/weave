"""实时通道鉴权：WebSocket 与 SSE 都必须带有效凭证

/ws 与 /events 曾经完全不校验，任何知道地址的人都能订阅跨用户事件。
现在两者都要求 access token，这里锁住拒绝路径，避免回退成匿名可订阅。
"""
import pytest
from starlette.websockets import WebSocketDisconnect

from app.main import _verify_sse_token


def _token(client, phone="13900007777"):
    r = client.post("/api/v1/auth/register", json={
        "phone": phone, "password": "Test123456!", "name": phone, "role": "elderly",
    })
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_ws_without_token_is_closed(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/ws") as ws:
            ws.receive_text()
    assert exc.value.code == 4001


def test_ws_with_invalid_token_is_closed(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/ws?token=not-a-jwt") as ws:
            ws.receive_text()
    assert exc.value.code == 4001


def test_ws_valid_token_can_ping(client):
    token = _token(client)
    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        ws.send_json({"type": "ping"})
        reply = ws.receive_json()
        assert reply["type"] == "pong"


def test_sse_verify_accepts_only_real_access_tokens(client):
    token = _token(client, "13900008888")
    assert _verify_sse_token(token) is True
    assert _verify_sse_token("") is False
    assert _verify_sse_token("bad.token.value") is False


def test_sse_and_ws_endpoints_reject_anonymous(client):
    assert client.get("/events").status_code == 401
    assert client.get("/events?token=garbage").status_code == 401
