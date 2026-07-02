"""Redis 客户端单例

用于限流、SSE Pub/Sub、token 黑名单等需要跨实例共享的场景。
测试环境或未配置 Redis 时降级到内存模式，保证开发体验。
"""
import os
import logging
from typing import Optional

logger = logging.getLogger("cognitive_garden")

_redis = None
_redis_available = False


def init_redis() -> bool:
    """初始化 Redis 连接，返回是否可用"""
    global _redis, _redis_available

    # 测试环境跳过 Redis，用内存模式
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("CG_DISABLE_REDIS"):
        _redis_available = False
        return False

    try:
        import redis
        from app.config import get_settings
        settings = get_settings()

        _redis = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=True,
        )
        _redis.ping()
        _redis_available = True
        logger.info("Redis 已连接: %s", settings.redis_url)
        return True
    except ImportError:
        logger.warning("redis 库未安装，限流/SSE/黑名单将降级到内存模式")
        _redis_available = False
        return False
    except Exception as e:
        logger.warning("Redis 连接失败，降级到内存模式: %s", e)
        _redis_available = False
        return False


def get_redis():
    """获取 Redis 客户端，不可用时返回 None"""
    return _redis if _redis_available else None


def is_redis_available() -> bool:
    return _redis_available


# ========== 内存降级实现（单实例时使用）==========
_mem_store: dict = {}
_mem_buckets: dict = {}
_mem_pubsub_channels: dict = {}


def mem_set(key: str, value: str, ttl: Optional[int] = None) -> bool:
    import time
    _mem_store[key] = {"value": value, "expire": time.time() + ttl if ttl else None}
    return True


def mem_get(key: str) -> Optional[str]:
    import time
    item = _mem_store.get(key)
    if not item:
        return None
    if item["expire"] and time.time() > item["expire"]:
        _mem_store.pop(key, None)
        return None
    return item["value"]


def mem_delete(key: str) -> int:
    if key in _mem_store:
        _mem_store.pop(key, None)
        return 1
    return 0


# ========== Token 黑名单（access token 主动吊销）==========
_BLACKLIST_PREFIX = "cg:token_blacklist:"


def blacklist_token(jti: str, ttl_seconds: int) -> bool:
    """将 access token 的 jti 加入黑名单，TTL 到期自动清理"""
    if not jti:
        return False
    key = _BLACKLIST_PREFIX + jti
    r = get_redis()
    if r is not None:
        r.setex(key, ttl_seconds, "1")
        return True
    return mem_set(key, "1", ttl_seconds)


def is_token_blacklisted(jti: str) -> bool:
    """检查 jti 是否在黑名单中"""
    if not jti:
        return False
    key = _BLACKLIST_PREFIX + jti
    r = get_redis()
    if r is not None:
        return r.exists(key) > 0
    return mem_get(key) is not None
