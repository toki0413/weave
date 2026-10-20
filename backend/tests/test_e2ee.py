"""v2 语音留言加密测试：每消息内容密钥 + 逐接收方包装

回归背景（2026-10）：v1 的 HKDF(master_key, salt=对方id) 协商在双方持有
不同 master key 时无法得到同一把密钥，方案在数学上不成立。v2 改为
每消息独立内容密钥 + 各方用自己的 master_key 包装/解包。
"""
import base64
import os

import pytest

from app.services.e2ee import (
    encrypt_family_message,
    add_recipient_wrap,
    unwrap_content_key,
    decrypt_family_message,
    encrypt_for_recipient,
    decrypt_from_sender,
    derive_wrapping_key,
    derive_server_storage_key,
)
from app.services.crypto import generate_master_key


SENDER_ID = "user-sender"
RECV_ID = "user-receiver"
PLAINTEXT = "data:audio/webm;base64,SGVsbG8gVm9pY2U="


def test_v2_roundtrip_sender():
    """发送方用自己的 master_key 可解密"""
    mk = generate_master_key()
    envelope = encrypt_family_message(PLAINTEXT, SENDER_ID, mk)
    assert envelope["v"] == 2
    assert decrypt_family_message(envelope, SENDER_ID, mk) == PLAINTEXT


def test_v2_recipient_wrap_and_decrypt():
    """接收方补写包装后用自己的 master_key 解密，与发送方密钥无关"""
    sender_mk = generate_master_key()
    recv_mk = generate_master_key()
    assert sender_mk != recv_mk
    envelope = encrypt_family_message(PLAINTEXT, SENDER_ID, sender_mk)
    # 补写是幂等的
    env2 = add_recipient_wrap(envelope, RECV_ID, recv_mk)
    env3 = add_recipient_wrap(env2, RECV_ID, recv_mk)
    assert env3["key_wraps"][RECV_ID] == env2["key_wraps"][RECV_ID]
    assert decrypt_family_message(env3, RECV_ID, recv_mk) == PLAINTEXT


def test_v2_wrong_master_key_fails():
    """错误的 master_key 解包应失败"""
    sender_mk = generate_master_key()
    recv_mk = generate_master_key()
    attacker_mk = generate_master_key()
    envelope = encrypt_family_message(PLAINTEXT, SENDER_ID, sender_mk)
    envelope = add_recipient_wrap(envelope, RECV_ID, recv_mk)
    with pytest.raises(Exception):
        decrypt_family_message(envelope, RECV_ID, attacker_mk)


def test_v2_missing_wrap_raises():
    """未补写包装的用户解包应抛 KeyError"""
    mk = generate_master_key()
    envelope = encrypt_family_message(PLAINTEXT, SENDER_ID, mk)
    with pytest.raises(KeyError):
        unwrap_content_key(envelope, "nobody", mk)


def test_v2_content_key_unique_per_message():
    """每条消息的内容密钥应独立随机"""
    mk = generate_master_key()
    e1 = encrypt_family_message("a", SENDER_ID, mk)
    e2 = encrypt_family_message("a", SENDER_ID, mk)
    k1 = unwrap_content_key(e1, SENDER_ID, mk)
    k2 = unwrap_content_key(e2, SENDER_ID, mk)
    assert k1 != k2


def test_v2_server_storage_key_stable():
    """server storage key 从配置派生，同配置下稳定（接收方补写依赖它）"""
    assert derive_server_storage_key() == derive_server_storage_key()
    assert len(derive_server_storage_key()) == 32


def test_v1_scheme_broken_by_design_documented():
    """文档化 v1 缺陷：双方 master key 不同时，v1 无法互相解密。

    该测试固化 v1 被替换的原因：encrypt_for_recipient 用
    HKDF(sender_mk, salt=recipient_id)，decrypt_from_sender 用
    HKDF(recipient_mk, salt=sender_id)，两式相等仅当双方共享同一密钥。
    """
    sender_mk = generate_master_key()
    recv_mk = generate_master_key()
    envelope = encrypt_for_recipient("hello", sender_mk, RECV_ID)
    with pytest.raises(Exception):
        decrypt_from_sender(
            envelope["ciphertext"], envelope["iv"], envelope["tag"], recv_mk, SENDER_ID
        )


def test_wrapping_key_purpose_isolation():
    """包装密钥用途隔离：不同 master_key 派生不同包装密钥"""
    k1 = derive_wrapping_key(generate_master_key())
    k2 = derive_wrapping_key(generate_master_key())
    assert k1 != k2
    assert len(k1) == 32
