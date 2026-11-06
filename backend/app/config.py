import os
import secrets
import json
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pathlib import Path

# 持久化生成的密钥，避免每次重启后 token 失效
def _load_or_create_secret() -> str:
    env_key = os.getenv("CG_JWT_SECRET")
    if env_key:
        return env_key

    secret_file = Path.home() / ".cognitive-garden" / "secret.json"
    try:
        if secret_file.exists():
            data = json.loads(secret_file.read_text(encoding="utf-8"))
            if data.get("secret_key"):
                return data["secret_key"]
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        new_key = secrets.token_hex(32)
        secret_file.write_text(json.dumps({"secret_key": new_key}), encoding="utf-8")
        try:
            os.chmod(secret_file, 0o600)
        except OSError:
            pass
        return new_key
    except Exception:
        return secrets.token_hex(32)

class Settings(BaseSettings):
    app_name: str = "Cognitive Garden API"
    debug: bool = Field(False, validation_alias=AliasChoices("CG_DEBUG", "debug"))

    # Database — 生产用 PostgreSQL，开发/测试可回退 SQLite
    database_url: str = Field(
        "sqlite:///./cognitive_garden.db",
        validation_alias=AliasChoices("CG_DATABASE_URL", "database_url", "DATABASE_URL"),
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 3600

    # Redis — 限流、SSE Pub/Sub、token 黑名单共享存储
    redis_url: str = Field(
        "redis://localhost:6379/0",
        validation_alias=AliasChoices("CG_REDIS_URL", "redis_url", "REDIS_URL"),
    )

    # Security
    secret_key: str = Field(
        default_factory=_load_or_create_secret,
        validation_alias=AliasChoices("CG_JWT_SECRET", "secret_key"),
    )
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30          # access token 30 分钟
    refresh_token_expire_days: int = 7              # refresh token 7 天

    # 对外来源白名单（逗号分隔）。Web 部署须显式加入站点域名，
    # 否则浏览器跨域请求被拒；同源反代部署可留空。
    cors_origins: str = Field(
        "", validation_alias=AliasChoices("CG_CORS_ORIGINS", "cors_origins"))
    # 是否信任 X-Forwarded-For（仅当前置反代可信时开启，否则可被伪造绕过限流）
    trust_proxy: bool = Field(
        False, validation_alias=AliasChoices("CG_TRUST_PROXY", "trust_proxy"))

    # 可观测端点访问控制：/metrics 与 /events
    metrics_token: str = Field(
        "", validation_alias=AliasChoices("CG_METRICS_TOKEN", "metrics_token"))
    # 语音留言密文目录是否作为静态资源对外暴露（默认关闭：仅内部读取）
    serve_uploads: bool = Field(
        False, validation_alias=AliasChoices("CG_SERVE_UPLOADS", "serve_uploads"))

    # 上传体积上限（STT 音频 / 备份导入）
    max_audio_upload_mb: int = 10
    max_backup_import_mb: int = 10

    # 登录防爆破：同一账号连续失败达到阈值后锁定
    login_max_failures: int = 5
    login_lockout_minutes: int = 15

    # 迁移失败时是否允许降级 create_all（仅开发；生产必须 fail-fast）
    allow_create_all_fallback: bool = Field(
        False,
        validation_alias=AliasChoices("CG_ALLOW_CREATE_ALL", "allow_create_all_fallback"))

    # KMS — 主密钥包装密钥的托管方式
    # file:  持久化到用户目录（单机默认，重启后数据仍可解密）
    # env:   从环境变量 CG_KMS_MASTER_KEY 读取
    # aws:   AWS KMS（需配置 CG_KMS_KEY_ID + AWS 凭证）
    # local: 进程内随机密钥（不安全，重启后已加密数据无法解密）
    kms_provider: str = Field(
        "file", validation_alias=AliasChoices("CG_KMS_PROVIDER", "kms_provider"))
    kms_master_key: str = Field(
        "", validation_alias=AliasChoices("CG_KMS_MASTER_KEY", "kms_master_key"))
    kms_key_id: str = Field(
        "", validation_alias=AliasChoices("CG_KMS_KEY_ID", "kms_key_id"))
    kms_aws_region: str = Field(
        "", validation_alias=AliasChoices("CG_KMS_AWS_REGION", "kms_aws_region"))

    # ASR (离线优先，Vosk 为默认引擎；链式降级见 services/asr_providers)
    asr_provider: str = "vosk"  # vosk | bailian | volc | none
    asr_model_path: str = ""
    # 火山引擎一句话识别（豆包语音同源，官方场景含老人方言对话）；三项齐备才启用
    asr_volc_app_id: str = ""
    asr_volc_token: str = ""
    asr_volc_cluster: str = ""
    asr_volc_timeout: float = 15.0   # WebSocket 单次识别超时（原内联版硬编码值）
    # Google 在线降级：境内网络不可达，默认关闭；部署方显式开启后才走在线降级
    stt_online_fallback: bool = False

    # 阿里云百炼 DashScope（OpenAI 兼容端点，复用 httpx，不引 dashscope SDK）
    bailian_api_key: str = ""       # 留空则百炼整体关闭，回到 vosk-only
    bailian_workspace_id: str = ""  # 业务空间专属域名用，空则用公共端点
    bailian_region: str = "cn-beijing"
    bailian_base_url: str = ""      # 显式覆盖；空则由 workspace/region 推导
    bailian_asr_model: str = "qwen3-asr-flash"
    bailian_asr_timeout: float = 25.0
    bailian_context_words_max: int = 2000  # system context 字符上限

    # LLM (可选，仅在用户配置时启用)
    llm_provider: str = ""  # 留空表示不使用 LLM
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = ""  # 自定义 provider 端点，为空时使用默认

    # 审计日志
    audit_log_enabled: bool = True

    # 漏录日课提醒（W3 方案 A：进程内日任务 + Redis 锁去重）
    missed_checkin_enabled: bool = True
    missed_checkin_hour: int = 20                    # 北京时间几点扫
    missed_checkin_threshold_days: int = 2           # 连续几天没记录才提醒

    # 家属周摘要（G5：进程内周任务 + Redis 周锁，骨架同漏录提醒）
    weekly_digest_enabled: bool = True
    weekly_digest_weekday: int = 0                   # 0=周一 … 6=周日
    weekly_digest_hour: int = 10                     # 北京时刻

    # 告警出站触达（G1）：warning 及以上告警推到应用外。全部留空即关闭，
    # 应用内通知不受影响。邮件按家属 notify_email 逐人发送；
    # webhook 填企业微信群机器人地址（config-only 接入值守群）。
    alert_outbound_min_severity: str = "warning"     # info 不出站
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""                              # 留空用 smtp_user
    smtp_use_ssl: bool = True                        # 465 走 SSL；587 改 False + STARTTLS
    alert_webhook_url: str = ""                      # 企业微信群机器人 webhook 地址

    model_config = SettingsConfigDict(env_file=".env")

@lru_cache()
def get_settings() -> Settings:
    return Settings()
