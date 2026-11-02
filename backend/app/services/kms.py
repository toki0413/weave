"""KMS/HSM 抽象层

为应用提供主密钥的包装/解包服务。主密钥本身不再依赖用户密码派生，
而是由 KMS 统一管理：密码只用于身份认证，不再承担加密职责。

支持三种 provider：
- file:  持久化到用户目录的随机密钥（单机默认，重启后数据仍可解密）
- env:   从环境变量 CG_KMS_MASTER_KEY 读取的对称密钥（适合单机部署）
- aws:   AWS KMS，使用 envelope encryption（生产推荐）
- local: 进程内随机密钥，仅开发用（重启后已加密数据无法解密）

选型建议：
  开发/测试 → file（默认）
  单机生产  → env（配合强随机密钥 + OS 密钥管理）
  云上生产  → aws
"""
import base64
import logging
import os
import secrets
from pathlib import Path
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


class FileKMS(KMSProvider):
    """文件 KMS：进程内随机生成包装密钥，持久化到用户目录（0o600）。

    与 local 的区别：重启后密钥仍在，已加密数据可继续解密——单机默认选项。
    与 env 的区别：无需手工配置环境变量；密钥与数据同机存放，防护等级
    等同于磁盘安全级别，多机/生产环境仍应使用 env 或 aws。

    恢复路径（G3）：wrap key 与数据同机意味着磁盘故障/误删 = 全部 E2EE
    内容永久不可解。export_wrap_key / import_wrap_key 提供密钥备份与
    恢复；部署方应在首次启用后立即导出备份（配合 /backup/kms-wrap-key）。
    """

    def __init__(self):
        self.key_file = Path.home() / ".cognitive-garden" / "kms_wrap_key.bin"
        try:
            key_file = self.key_file
            key_file.parent.mkdir(parents=True, exist_ok=True)
            if key_file.exists():
                self._key = key_file.read_bytes()
                if len(self._key) != 32:
                    raise ValueError("kms_wrap_key.bin 长度异常，需删除后重新生成")
            else:
                self._key = secrets.token_bytes(32)
                key_file.write_bytes(self._key)
            try:
                os.chmod(key_file, 0o600)
            except OSError:
                pass
            logger.info("FileKMS 启用：包装密钥已持久化到 %s", key_file)
        except OSError as e:
            # 无可写目录时退化为进程内密钥，行为等同 local
            logger.warning("FileKMS 无法持久化密钥（%s），退化为 local 行为", e)
            self._key = secrets.token_bytes(32)

    def generate_data_key(self) -> Tuple[bytes, str]:
        plaintext = generate_master_key()
        encrypted = encrypt(base64.b64encode(plaintext).decode("ascii"), self._key)
        return plaintext, encrypted

    def decrypt_data_key(self, encrypted_b64: str) -> bytes:
        plaintext_b64 = decrypt(encrypted_b64, self._key)
        return base64.b64decode(plaintext_b64)

    def export_wrap_key(self) -> str:
        return base64.b64encode(self._key).decode("ascii")

    def import_wrap_key(self, key_b64: str) -> None:
        """从备份恢复 wrap key：校验 → 落盘（0o600）→ 热替换进程内密钥"""
        try:
            raw = base64.b64decode(key_b64, validate=True)
        except Exception as e:
            raise ValueError(f"wrap key 不是合法的 base64：{e}")
        if len(raw) != 32:
            raise ValueError("wrap key 解码后必须为 32 字节")
        try:
            self.key_file.parent.mkdir(parents=True, exist_ok=True)
            self.key_file.write_bytes(raw)
            try:
                os.chmod(self.key_file, 0o600)
            except OSError:
                pass
        except OSError as e:
            raise RuntimeError(f"wrap key 无法持久化：{e}")
        self._key = raw
        logger.warning("FileKMS wrap key 已从备份恢复到 %s", self.key_file)


def init_kms() -> KMSProvider:
    """根据配置初始化 KMS provider 单例"""
    global _provider
    if _provider is not None:
        return _provider

    settings = get_settings()
    provider = (settings.kms_provider or "file").lower()

    if provider == "aws":
        _provider = AWSKMS(settings.kms_key_id, settings.kms_aws_region)
    elif provider == "env":
        if not settings.kms_master_key:
            raise ValueError("env KMS 模式需要配置 CG_KMS_MASTER_KEY")
        _provider = EnvKMS(settings.kms_master_key)
    elif provider == "file":
        _provider = FileKMS()
    elif provider == "local":
        _provider = LocalKMS()
    else:
        raise ValueError(f"未知 KMS provider: {provider}（可选: file/local/env/aws）")

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


# ============ 恢复路径（G3）============
# wrap key 丢失 = 全部 E2EE 内容永久不可解。这三个函数是恢复路径的
# 服务层入口；HTTP 出口在 routers/backup.py（admin-only + 限流）。

def describe_kms() -> dict:
    """当前 KMS provider 的恢复路径状态，供运维自检"""
    p = get_kms()
    info: dict = {"provider": type(p).__name__, "exportable": False, "key_file": None}
    if isinstance(p, FileKMS):
        info.update({
            "exportable": True,
            "key_file": str(p.key_file),
            "key_file_exists": p.key_file.exists(),
            "message": "wrap key 与数据同机存放，请立即通过 /backup/kms-wrap-key 导出备份",
        })
    elif isinstance(p, EnvKMS):
        info["message"] = "主密钥由环境变量 CG_KMS_MASTER_KEY 托管，备份由部署密钥管理体系负责"
    elif isinstance(p, AWSKMS):
        info["message"] = "主密钥由 AWS KMS 托管，备份由 AWS 侧负责（KMS 密钥不可导出）"
    else:  # LocalKMS
        info["message"] = "local KMS 密钥仅存于进程内存，无恢复路径；请切换到 file/env/aws"
    return info


def export_wrap_key() -> str:
    """导出 wrap key（base64）。仅 file provider 支持；其余 provider 的
    密钥由外部体系托管，导出既无必要也无权限。"""
    p = get_kms()
    if not isinstance(p, FileKMS):
        raise ValueError(
            f"当前 KMS provider（{type(p).__name__}）不支持密钥导出：密钥由外部体系托管")
    return p.export_wrap_key()


def import_wrap_key(key_b64: str) -> None:
    """从备份恢复 wrap key（base64）。恢复后立即热替换进程内密钥，
    无需重启即可继续解包历史数据密钥。"""
    p = get_kms()
    if not isinstance(p, FileKMS):
        raise ValueError(
            f"当前 KMS provider（{type(p).__name__}）不支持密钥导入：密钥由外部体系托管")
    p.import_wrap_key(key_b64)
