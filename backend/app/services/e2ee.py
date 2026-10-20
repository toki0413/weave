"""语音留言加密服务（v2：每消息内容密钥 + 逐接收方包装）

历史说明：v1 尝试"端到端"密钥协商（HKDF(master_key, salt=对方id)），但加密方
与解密方要得到同一把密钥，仅当双方共享同一 master key——设计不成立。

v2 设计（2026-10 重构）：
- 每条消息生成独立随机内容密钥（content_key），AES-256-GCM 加密消息体
- content_key 为发送方即时包装、为接收方在其首次拉取时补写（各自用自己
  的 master_key 派生包装密钥），此后读取不再依赖服务端可解
- 补写依赖 server_wrap（服务端存储包装），故该方案如实定性为
  【服务端中转加密】：服务端有能力恢复消息明文，不是端到端加密
- 升级路径：用户长期 X25519 身份密钥对 + ECDH，服务端仅中转公钥
"""
import base64
import os
from typing import Dict, List, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from app.services.crypto import _KEY_LENGTH, _NONCE_LENGTH, encrypt, decrypt


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


# ============================================================
# v2：每消息内容密钥 + 逐接收方包装（2026-10 重构）
#
# v1 的密钥协商在数学上不成立：加密方用 HKDF(sender_mk, salt=recipient_id)，
# 解密方用 HKDF(recipient_mk, salt=sender_id)，两式相等仅当双方持有同一把
# master key——意味着全家共享主密钥、服务端可见一切，"端到端"名不副实。
#
# v2 设计：
# 1. 每条消息生成独立随机内容密钥（content_key），加密消息体
# 2. content_key 用每个授权方的 master_key（HKDF 派生的包装密钥）分别包装
# 3. 各方用【自己的】master_key 解包自己的 key_wrap，互不依赖对方密钥
# 4. 发送时服务端只有发送方密钥缓存：接收方的 key_wrap 在接收方首次拉取时
#    由服务端补写（lazy wrap），此后无需再依赖发送方在线
# 安全边界（如实声明）：服务端在包装/解包瞬间可见 content_key 明文，
# 属于"服务端中转加密"（transport-at-rest），不是端到端加密。
# 升级路径：用户侧长期 X25519 身份密钥对 + ECDH 协商，服务端仅中转公钥。
# ============================================================

_WRAP_SALT = "voice-message-content-key"
_WRAP_INFO = b"cognitive-garden-e2ee-v2"
_SERVER_SALT = "voice-message-server-storage"


def derive_wrapping_key(master_key: bytes) -> bytes:
    """从用户 master_key 派生内容密钥包装密钥（用途隔离，不与 v1 共用盐）"""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=_KEY_LENGTH,
        salt=_WRAP_SALT.encode("utf-8"),
        info=_WRAP_INFO,
    )
    return hkdf.derive(master_key)


def derive_server_storage_key() -> bytes:
    """服务端存储包装密钥：从 JWT secret 用途隔离派生。

    存在意义：接收方首次拉取时服务端需补写其 key_wrap，而彼时 content_key
    明文已不可得，因此创建时额外留一份 server_wrap。代价是服务端始终有
    能力恢复明文——本方案因此定性为服务端中转加密。
    """
    from app.config import get_settings
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=_KEY_LENGTH,
        salt=_SERVER_SALT.encode("utf-8"),
        info=_WRAP_INFO,
    )
    return hkdf.derive(get_settings().secret_key.encode("utf-8"))


def encrypt_family_message(plaintext: str, sender_id: str, sender_master_key: bytes) -> dict:
    """v2 加密：随机 content_key 加密消息体；为发送方包装并留 server_wrap。

    接收方的 key_wrap 在其首次拉取时由 add_recipient_wrap 补写。
    """
    content_key = os.urandom(_KEY_LENGTH)
    content = encrypt_message(plaintext, content_key)
    sender_wrap = encrypt_message(
        base64.b64encode(content_key).decode("ascii"), derive_wrapping_key(sender_master_key)
    )
    server_wrap = encrypt(
        base64.b64encode(content_key).decode("ascii"), derive_server_storage_key()
    )
    return {"v": 2, "content": content, "key_wraps": {sender_id: sender_wrap}, "server_wrap": server_wrap}


def add_recipient_wrap(envelope: dict, user_id: str, user_master_key: bytes) -> dict:
    """为接收方补写 key_wrap（首次拉取时调用，幂等）。

    用 server_wrap 恢复 content_key，再用该用户自己的包装密钥包装。
    """
    key_wraps = envelope.setdefault("key_wraps", {})
    if user_id in key_wraps:
        return envelope
    server_wrap = envelope.get("server_wrap")
    if not server_wrap:
        raise ValueError("envelope 缺少 server_wrap，无法补写接收方包装")
    content_key_b64 = decrypt(server_wrap, derive_server_storage_key())
    key_wraps[user_id] = encrypt_message(
        content_key_b64, derive_wrapping_key(user_master_key)
    )
    return envelope


def unwrap_content_key(envelope: dict, user_id: str, user_master_key: bytes) -> bytes:
    """用用户自己的 master_key 解包 content_key。密钥错误时抛 InvalidTag。"""
    key_wraps = envelope.get("key_wraps") or {}
    if user_id not in key_wraps:
        raise KeyError(f"没有 {user_id} 的密钥包装")
    wrap = key_wraps[user_id]
    wrapping_key = derive_wrapping_key(user_master_key)
    return base64.b64decode(decrypt_message(
        wrap["ciphertext"], wrap["iv"], wrap["tag"], wrapping_key
    ))


def decrypt_family_message(envelope: dict, user_id: str, user_master_key: bytes) -> str:
    """v2 解密：用户用自己的 master_key 解包 content_key，再解消息体。"""
    content_key = unwrap_content_key(envelope, user_id, user_master_key)
    content = envelope["content"]
    ct = base64.b64decode(content["ciphertext"])
    tag = base64.b64decode(content["tag"])
    nonce = base64.b64decode(content["iv"])
    aesgcm = AESGCM(content_key)
    return aesgcm.decrypt(nonce, ct + tag, None).decode("utf-8")
