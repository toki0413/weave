import os
import secrets
import json
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
    debug: bool = False

    # Database
    database_url: str = "sqlite:///./cognitive_garden.db"

    # Security
    secret_key: str = _load_or_create_secret()
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # ASR (离线优先，Vosk 为默认引擎)
    asr_provider: str = "vosk"  # vosk | whisper | none
    asr_model_path: str = ""

    # LLM (可选，仅在用户配置时启用)
    llm_provider: str = ""  # 留空表示不使用 LLM
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = ""  # 自定义 provider 端点，为空时使用默认

    model_config = SettingsConfigDict(env_file=".env")

@lru_cache()
def get_settings() -> Settings:
    return Settings()
