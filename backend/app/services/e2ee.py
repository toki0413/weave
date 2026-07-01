"""端到端加密服务：基于用户主密钥派生通信密钥

设计：
- derive_communication_key：用 HKDF-SHA256 从 master_key + salt 派生通信密钥
- encrypt_message / decrypt_message：AES-256-GCM
- encrypt_for_recipient：发送方使用 master_key + recipient_id 派生共享密钥
"""
import base64
import json
import os
import hashlib
import hmac

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from app.services.crypto import _KEY_LENGTH, _NONCE_LENGTH


def derive_communication_key(master_key: bytes, salt: str) -> bytes:
    """使用 HKDF-SHA256 从 master_key 派生通信密钥

    salt 建议格式：f"{user_id}:communication"
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=_KEY_LENGTH,
        salt=salt.encode("utf-8"),
        info=b"cognitive-garden-e2ee-v1",
    )
    return hkdf.derive(master_key)


def encrypt_message(plaintext: str, key: bytes) -> dict:
    """AES-256-GCM 加密，返回 {ciphertext, iv, tag} 对象

    ciphertext 和 tag 以 base64 字符串返回。
    """
    nonce = os.urandom(_NONCE_LENGTH)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # ct 末尾是 16 字节 tag
    ciphertext = ct[:-16]
    tag = ct[-16:]
    return {
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        "iv": base64.b64encode(nonce).decode("ascii"),
        "tag": base64.b64encode(tag).decode("ascii"),
    }


def decrypt_message(ciphertext: str, iv: str, tag: str, key: bytes) -> str:
    """解密 AES-256-GCM 密文

    ciphertext, iv, tag 均为 base64 字符串。
    """
    ct = base64.b64decode(ciphertext)
    nonce = base64.b64decode(iv)
    auth_tag = base64.b64decode(tag)
    aesgcm = AESGCM(key)
    # AESGCM 要求 ciphertext + tag 拼接
    plaintext = aesgcm.decrypt(nonce, ct + auth_tag, None)
    return plaintext.decode("utf-8")


def encrypt_for_recipient(plaintext: str, sender_master_key: bytes, recipient_id: str) -> dict:
    """发送方使用自己的 master_key + recipient_id 派生共享密钥，加密消息。

    接收方用相同方式（自己的 master_key + sender_id）派生相同密钥解密。
    这里的共享密钥 = HKDF(master_key, salt=f"{recipient_id}:shared"))
    """
    salt = f"{recipient_id}:shared"
    shared_key = derive_communication_key(sender_master_key, salt)
    return encrypt_message(plaintext, shared_key)


def decrypt_from_sender(ciphertext: str, iv: str, tag: str, recipient_master_key: bytes, sender_id: str) -> str:
    """接收方使用自己的 master_key + sender_id 派生共享密钥，解密消息。"""
    salt = f"{sender_id}:shared"
    shared_key = derive_communication_key(recipient_master_key, salt)
    return decrypt_message(ciphertext, iv, tag, shared_key)
