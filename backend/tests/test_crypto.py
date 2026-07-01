"""加密模块和加密存储相关测试"""
import base64

import pytest

from app.services.crypto import (
    derive_key,
    encrypt,
    decrypt,
    encrypt_json,
    decrypt_json,
)
from app.services import key_manager
from app.services.scales import SCALES


# 固定的测试参数，方便断言
SALT = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
PASSWORD = "test_password_123"


# ========== 密钥派生 ==========
def test_derive_key_consistent():
    """相同密码和 salt 应派生出相同密钥"""
    k1 = derive_key(PASSWORD, SALT)
    k2 = derive_key(PASSWORD, SALT)
    assert k1 == k2
    assert len(k1) == 32  # 256 位 = 32 字节


def test_derive_key_different_password():
    """不同密码应派生出不同密钥"""
    k1 = derive_key(PASSWORD, SALT)
    k2 = derive_key("another_password", SALT)
    assert k1 != k2


def test_derive_key_different_salt():
    """不同 salt 应派生出不同密钥"""
    k1 = derive_key(PASSWORD, SALT)
    k2 = derive_key(PASSWORD, "0123456789abcdef0123456789abcdef")
    assert k1 != k2


# ========== AES-256-GCM 加解密 ==========
def test_encrypt_decrypt_roundtrip():
    """加密解密往返应还原原文"""
    key = derive_key(PASSWORD, SALT)
    plaintext = "今天和老伴去公园散步，心情很好"
    ciphertext = encrypt(plaintext, key)
    assert ciphertext != plaintext
    assert decrypt(ciphertext, key) == plaintext


def test_encrypt_produces_different_ciphertext():
    """同一明文每次加密应产生不同密文（nonce 随机）"""
    key = derive_key(PASSWORD, SALT)
    plaintext = "同一段话"
    c1 = encrypt(plaintext, key)
    c2 = encrypt(plaintext, key)
    assert c1 != c2
    assert decrypt(c1, key) == plaintext
    assert decrypt(c2, key) == plaintext


def test_decrypt_wrong_key_fails():
    """用错误密钥解密应抛异常"""
    key1 = derive_key(PASSWORD, SALT)
    key2 = derive_key("wrong_password", SALT)
    ciphertext = encrypt("这是一段秘密内容", key1)
    with pytest.raises(Exception):
        decrypt(ciphertext, key2)


def test_ciphertext_is_base64():
    """密文应是合法的 base64 字符串"""
    key = derive_key(PASSWORD, SALT)
    ciphertext = encrypt("hello", key)
    # 能解码说明格式没问题
    raw = base64.b64decode(ciphertext)
    # nonce(12) + 至少 16 字节 tag，所以总长 > 28
    assert len(raw) > 28


# ========== JSON 加解密 ==========
def test_encrypt_decrypt_json_roundtrip():
    """JSON 加密解密往返"""
    key = derive_key(PASSWORD, SALT)
    obj = [
        {"question_id": "q1", "score": 1},
        {"question_id": "q2", "score": 0},
    ]
    ciphertext = encrypt_json(obj, key)
    assert isinstance(ciphertext, str)
    result = decrypt_json(ciphertext, key)
    assert result == obj


def test_encrypt_json_with_chinese():
    """JSON 加密解密含中文"""
    key = derive_key(PASSWORD, SALT)
    obj = {"text": "认知评估", "items": ["记忆", "计算", "语言"]}
    ciphertext = encrypt_json(obj, key)
    result = decrypt_json(ciphertext, key)
    assert result == obj


def test_decrypt_json_wrong_key_fails():
    """错误密钥解密 JSON 应失败"""
    key1 = derive_key(PASSWORD, SALT)
    key2 = derive_key("other", SALT)
    ciphertext = encrypt_json({"a": 1}, key1)
    with pytest.raises(Exception):
        decrypt_json(ciphertext, key2)


# ========== 密钥缓存 ==========
def test_key_manager_set_get_clear():
    """密钥缓存的基本读写和清除"""
    key_manager.clear_all()
    key_manager.set_user_keys("user-1", b"fake-kek-bytes", b"fake-master-key-bytes")
    assert key_manager.get_user_key("user-1") == b"fake-master-key-bytes"
    assert key_manager.get_user_kek("user-1") == b"fake-kek-bytes"
    assert key_manager.has_user_key("user-1") is True

    key_manager.clear_user_key("user-1")
    assert key_manager.has_user_key("user-1") is False
    with pytest.raises(RuntimeError):
        key_manager.get_user_key("user-1")


def test_key_manager_clear_all():
    """clear_all 应清空全部缓存"""
    key_manager.set_user_keys("u1", b"k1", b"m1")
    key_manager.set_user_keys("u2", b"k2", b"m2")
    key_manager.clear_all()
    assert not key_manager.has_user_key("u1")
    assert not key_manager.has_user_key("u2")


# ========== 会话加密存储 ==========
def test_session_encrypted_at_rest(client, auth_headers, db_session):
    """创建会话后数据库里是密文，API 返回明文"""
    from app.models import Session as DBSession

    text = "今天和老伴去公园散步"
    r = client.post(
        "/api/v1/session/",
        headers=auth_headers["headers"],
        json={"day_number": 1, "narrative_input": {"text": text}},
    )
    assert r.status_code == 200, r.text
    api_data = r.json()
    # API 返回的应该是明文
    assert api_data["narrative"] == text

    # 直接查数据库，确认存的是密文
    session_id = api_data["id"]
    db_session.expire_all()
    row = db_session.query(DBSession).filter(DBSession.id == session_id).first()
    assert row is not None
    assert row.is_encrypted is True
    assert row.narrative != text  # 不是明文
    # 密文应该是合法 base64
    base64.b64decode(row.narrative)


def test_session_list_returns_plaintext(client, auth_headers):
    """列表接口应返回解密后的明文"""
    text = "早上吃了包子，看了会儿电视"
    r = client.post(
        "/api/v1/session/",
        headers=auth_headers["headers"],
        json={"day_number": 1, "narrative_input": {"text": text}},
    )
    assert r.status_code == 200

    r = client.get("/api/v1/session/", headers=auth_headers["headers"])
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["narrative"] == text


def test_session_get_by_id_returns_plaintext(client, auth_headers):
    """按 id 查会话应返回解密后的明文"""
    text = "下午去了社区活动中心"
    r = client.post(
        "/api/v1/session/",
        headers=auth_headers["headers"],
        json={"day_number": 1, "narrative_input": {"text": text}},
    )
    sid = r.json()["id"]

    r = client.get(f"/api/v1/session/{sid}", headers=auth_headers["headers"])
    assert r.status_code == 200
    assert r.json()["narrative"] == text


# ========== 量表答案加密存储 ==========
def test_scale_answers_encrypted_at_rest(client, auth_headers, db_session):
    """提交量表后数据库里答案应为密文"""
    from app.models import ScaleRecord

    scale = SCALES["ad8"]
    answers = [{"question_id": q["id"], "score": 0} for q in scale["questions"]]
    r = client.post(
        "/api/v1/scale/ad8/submit",
        headers=auth_headers["headers"],
        json={"answers": answers},
    )
    assert r.status_code == 200, r.text
    record_id = r.json()["id"]

    db_session.expire_all()
    row = db_session.query(ScaleRecord).filter(ScaleRecord.id == record_id).first()
    assert row is not None
    assert row.is_encrypted is True
    # 加密后 answers 不再是原始列表，而是密文字符串
    assert not isinstance(row.answers, list)
    assert isinstance(row.answers, str)


def test_scale_history_still_works(client, auth_headers):
    """加密后历史查询应正常返回（不包含 answers 字段）"""
    scale = SCALES["ad8"]
    answers = [{"question_id": q["id"], "score": 0} for q in scale["questions"]]
    r = client.post(
        "/api/v1/scale/ad8/submit",
        headers=auth_headers["headers"],
        json={"answers": answers},
    )
    assert r.status_code == 200

    r = client.get("/api/v1/scale/history/all", headers=auth_headers["headers"])
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    assert data[0]["scale_type"] == "ad8"
    assert data[0]["total_score"] == 0
