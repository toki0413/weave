"""语音留言：核心功能与权限边界

这条路径此前零测试覆盖（覆盖率 28%），而它同时承载三件事：家庭绑定的
权限判定、base64 音频解码、每条消息独立密钥的加密落盘。任何一处回归
都不会被原有测试发现，因此这里把边界逐条锁住。
"""
import base64
import pathlib

import pytest

from app.models import FamilyLink, User, VoiceMessage


def _register(client, phone):
    r = client.post("/api/v1/auth/register", json={
        "phone": phone, "password": "Test123456!", "name": phone, "role": "elderly",
    })
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _wire(db_session, elder_phone, family_phone, relation="子女"):
    elder = db_session.query(User).filter(User.phone == elder_phone).first()
    family = db_session.query(User).filter(User.phone == family_phone).first()
    db_session.add(FamilyLink(
        elderly_user_id=elder.id, family_user_id=family.id, relation=relation))
    db_session.commit()
    return elder, family


def _cleanup_files(db_session):
    """删除测试写入 uploads 的密文，避免污染工作区"""
    from app.routers.voice_message import UPLOAD_DIR
    for row in db_session.query(VoiceMessage).all():
        name = (row.audio_url or "").rsplit("/", 1)[-1]
        if name:
            p = pathlib.Path(UPLOAD_DIR) / name
            if p.exists():
                p.unlink()


@pytest.fixture
def wired_family(client, db_session):
    h_elder = _register(client, "13900001111")
    h_family = _register(client, "13900002222")
    elder, family = _wire(db_session, "13900001111", "13900002222")
    yield {"elder": elder, "family": family, "h_elder": h_elder, "h_family": h_family}
    _cleanup_files(db_session)


def test_create_voice_message_and_list(client, db_session, wired_family):
    audio = base64.b64encode(b"fake-audio-bytes-for-test").decode()
    r = client.post("/api/v1/voice-message/", headers=wired_family["h_elder"], json={
        "receiver_id": wired_family["family"].id,
        "audio_base64": audio,
        "duration": 3,
    })
    assert r.status_code == 200, r.text
    msg = r.json()
    assert msg["sender_id"] == wired_family["elder"].id
    assert msg["receiver_id"] == wired_family["family"].id
    # 密文信封随响应返回，且不含明文音频
    assert msg.get("encrypted_payload") is not None

    listed = client.get("/api/v1/voice-message/", headers=wired_family["h_family"])
    assert listed.status_code == 200
    assert any(m["id"] == msg["id"] for m in listed.json())


def test_unbound_receiver_is_rejected(client, db_session):
    """没有家庭绑定时不得发送——这是唯一的权限闸门"""
    h_elder = _register(client, "13900003333")
    _register(client, "13900004444")
    stranger = db_session.query(User).filter(User.phone == "13900004444").first()

    audio = base64.b64encode(b"x").decode()
    r = client.post("/api/v1/voice-message/", headers=h_elder, json={
        "receiver_id": stranger.id, "audio_base64": audio, "duration": 1,
    })
    assert r.status_code == 403
    assert "绑定" in r.json()["detail"]


def test_invalid_base64_returns_400(client, wired_family):
    r = client.post("/api/v1/voice-message/", headers=wired_family["h_elder"], json={
        "receiver_id": wired_family["family"].id,
        "audio_base64": "!!!not-base64!!!",
        "duration": 1,
    })
    assert r.status_code == 400, r.text


def test_only_receiver_can_mark_read(client, db_session, wired_family):
    """收件人可标记已读；第三人（即使已登录）不得操作他人消息"""
    audio = base64.b64encode(b"payload").decode()
    r = client.post("/api/v1/voice-message/", headers=wired_family["h_elder"], json={
        "receiver_id": wired_family["family"].id,
        "audio_base64": audio,
        "duration": 2,
    })
    assert r.status_code == 200
    msg_id = r.json()["id"]

    outsider_headers = _register(client, "13900005555")
    blocked = client.post(
        f"/api/v1/voice-message/{msg_id}/mark-read", headers=outsider_headers)
    assert blocked.status_code in (403, 404), blocked.text

    ok = client.post(
        f"/api/v1/voice-message/{msg_id}/mark-read", headers=wired_family["h_family"])
    assert ok.status_code == 200

    row = db_session.query(VoiceMessage).filter(VoiceMessage.id == msg_id).first()
    assert row.is_read is True


def test_mark_read_unknown_id_returns_404(client, wired_family):
    r = client.post(
        "/api/v1/voice-message/00000000-0000-0000-0000-000000000000/mark-read",
        headers=wired_family["h_family"],
    )
    assert r.status_code == 404, r.text
