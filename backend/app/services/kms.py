"""KMS/HSM 抽象层

为应用提供主密钥的包装/解包服务。主密钥本身不再依赖用户密码派生，
而是由 KMS 统一管理：密码只用于身份认证，不再承担加密职责。

支持三种 provider：
- local: 进程内随机密钥，仅开发用（重启后已加密数据无法解密）
- env:   从环境变量 CG_KMS_MASTER_KEY 读取的对称密钥（适合单机部署）
- aws:   AWS KMS，使用 envelope encryption（生产推荐）

选型建议：
  开发/测试 → local
  单机生产  → env（配合强随机密钥 + OS 密钥管理）
  云上生产  → aws
"""
import base64
import logging
import secrets
from typing import Optional, Tuple

from app.config import get_settings
from app.services.crypto import encrypt, decrypt, generate_master_key

logger = logging.getLogger("cognitive_garden")


class KMSProvider:
    """KMS provider 抽象基类"""

    def generate_data_key(self) -> Tuple[bytes, str]:
        """生成新的数据密钥，返回 (plaintext, encrypted_b64)"""
        raise NotImplementedError

    def decrypt_data_key(self, encrypted_b64: str) -> bytes:
        """解密数据密钥，返回 plaintext bytes"""
        raise NotImplementedError


class LocalKMS(KMSProvider):
    """本地 KMS：用进程内随机密钥包装（仅开发用）

    进程退出后密钥丢失，重启后无法解包历史数据。
    """

    def __init__(self):
        # 进程内单例密钥，重启即失效
        self._key = secrets.token_bytes(32)
        logger.warning("LocalKMS 启用：仅适用于开发/测试，重启后已加密数据将无法解密")

    def generate_data_key(self) -> Tuple[bytes, str]:
        plaintext = generate_master_key()
        encrypted = encrypt(base64.b64encode(plaintext).decode("ascii"), self._key)
        return plaintext, encrypted

    def decrypt_data_key(self, encrypted_b64: str) -> bytes:
        plaintext_b64 = decrypt(encrypted_b64, self._key)
        return base64.b64decode(plaintext_b64)


class EnvKMS(KMSProvider):
    """环境变量 KMS：从 CG_KMS_MASTER_KEY 读取对称密钥

    密钥需为 base64 编码的 32 字节随机串，可通过如下方式生成：
      python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
    """

    def __init__(self, master_key_b64: str):
        try:
            self._key = base64.b64decode(master_key_b64)
        except Exception as e:
            raise ValueError(f"CG_KMS_MASTER_KEY 不是合法的 base64：{e}")
        if len(self._key) != 32:
            raise ValueError("CG_KMS_MASTER_KEY 解码后必须为 32 字节")
        logger.info("EnvKMS 启用：使用环境变量提供的主密钥")

    def generate_data_key(self) -> Tuple[bytes, str]:
        plaintext = generate_master_key()
        encrypted = encrypt(base64.b64encode(plaintext).decode("ascii"), self._key)
        return plaintext, encrypted

    def decrypt_data_key(self, encrypted_b64: str) -> bytes:
        plaintext_b64 = decrypt(encrypted_b64, self._key)
        return base64.b64decode(plaintext_b64)


class AWSKMS(KMSProvider):
    """AWS KMS：使用 envelope encryption（生产推荐）

    每个数据密钥由 AWS KMS 生成，明文短暂存在于内存，密文持久化到数据库。
    """

    def __init__(self, key_id: str, region: str):
        try:
            import boto3
        except ImportError:
            raise RuntimeError("AWS KMS 模式需要 boto3 库：pip install boto3")
        if not key_id:
            raise ValueError("AWS KMS 模式需要配置 CG_KMS_KEY_ID")
        self._key_id = key_id
        self._client = boto3.client("kms", region_name=region or "us-east-1")
        logger.info("AWSKMS 启用：使用 KMS key %s", key_id)

    def generate_data_key(self) -> Tuple[bytes, str]:
        resp = self._client.generate_data_key(
            KeyId=self._key_id,
            KeySpec="AES_256",
        )
        plaintext = resp["Plaintext"]
        encrypted = base64.b64encode(resp["CiphertextBlob"]).decode("ascii")
        return plaintext, encrypted

    def decrypt_data_key(self, encrypted_b64: str) -> bytes:
        ciphertext_blob = base64.b64decode(encrypted_b64)
        resp = self._client.decrypt(CiphertextBlob=ciphertext_blob)
        return resp["Plaintext"]


_provider: Optional[KMSProvider] = None


def init_kms() -> KMSProvider:
    """根据配置初始化 KMS provider 单例"""
    global _provider
    if _provider is not None:
        return _provider

    settings = get_settings()
    provider = (settings.kms_provider or "local").lower()

    if provider == "aws":
        _provider = AWSKMS(settings.kms_key_id, settings.kms_aws_region)
    elif provider == "env":
        if not settings.kms_master_key:
            raise ValueError("env KMS 模式需要配置 CG_KMS_MASTER_KEY")
        _provider = EnvKMS(settings.kms_master_key)
    elif provider == "local":
        _provider = LocalKMS()
    else:
        raise ValueError(f"未知 KMS provider: {provider}（可选: local/env/aws）")

    return _provider


def get_kms() -> KMSProvider:
    """获取 KMS provider 单例，未初始化则自动初始化"""
    if _provider is None:
        return init_kms()
    return _provider


def unwrap_master_key(encrypted_b64: str) -> bytes:
    """通过 KMS 解包主密钥"""
    return get_kms().decrypt_data_key(encrypted_b64)


def generate_master_key_with_wrap() -> Tuple[bytes, str]:
    """生成新主密钥并用 KMS 包装，返回 (plaintext, encrypted_b64)

    注册新用户时调用：KMS 生成新密钥，明文只在内存中短暂存在。
    """
    return get_kms().generate_data_key()
