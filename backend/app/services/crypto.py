"""应用层加密工具：用 AES-256-GCM 保护敏感字段

密钥从用户密码 + salt 通过 PBKDF2 派生，不落盘。
每条记录独立 nonce，密文格式 base64(nonce + ciphertext + tag)。
"""
import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

# PBKDF2 迭代次数，兼顾安全性和性能
_PBKDF2_ITERATIONS = 200_000
_KEY_LENGTH = 32       # AES-256 需要 32 字节密钥
_NONCE_LENGTH = 12     # GCM 推荐 96 位 nonce


def derive_key(password: str, salt: str) -> bytes:
    """用 PBKDF2 从用户密码派生 256 位加密密钥

    salt 传十六进制字符串，内部转回字节。
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_KEY_LENGTH,
        salt=bytes.fromhex(salt),
        iterations=_PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt(plaintext: str, key: bytes) -> str:
    """AES-256-GCM 加密，返回 base64(nonce + ciphertext + tag)"""
    nonce = os.urandom(_NONCE_LENGTH)
    aesgcm = AESGCM(key)
    # AESGCM.encrypt 返回 ciphertext + tag 拼接的字节
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt(ciphertext_b64: str, key: bytes) -> str:
    """解密 base64(nonce + ciphertext + tag) 格式的密文"""
    raw = base64.b64decode(ciphertext_b64)
    nonce = raw[:_NONCE_LENGTH]
    ct = raw[_NONCE_LENGTH:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None).decode("utf-8")


def encrypt_json(obj, key: bytes) -> str:
    """加密可 JSON 序列化的对象"""
    return encrypt(json.dumps(obj, ensure_ascii=False), key)


def decrypt_json(ciphertext_b64: str, key: bytes):
    """解密并还原为 JSON 对象"""
    return json.loads(decrypt(ciphertext_b64, key))


# ========== 主密钥管理 ==========
# 业务数据（narrative / scale answers）改由随机主密钥加密，
# 主密钥本身再用用户密码派生的 KEK 加密后存入数据库。
# 这样修改密码时只需重新包装主密钥，无需重加密所有历史数据。


def generate_master_key() -> bytes:
    """生成 256-bit 随机主密钥"""
    return os.urandom(_KEY_LENGTH)


def wrap_master_key(master_key: bytes, kek: bytes) -> str:
    """用 KEK 加密主密钥，返回 base64(nonce + ciphertext + tag)"""
    return encrypt(base64.b64encode(master_key).decode("ascii"), kek)


def unwrap_master_key(wrapped: str, kek: bytes) -> bytes:
    """用 KEK 解密主密钥"""
    return base64.b64decode(decrypt(wrapped, kek))
