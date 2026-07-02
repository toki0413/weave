"""速率限制依赖

生产环境使用 Redis 滑动窗口，支持多实例共享限流计数。
无 Redis 时降级到内存滑动窗口（单实例有效）。
"""
import os
import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, HTTPException, Depends

from app.redis_client import get_redis, is_redis_available, _mem_buckets


def _get_client_ip(request: Request) -> str:
    """获取客户端 IP，优先处理反向代理转发头"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _mem_clean_bucket(key: str, window: float) -> None:
    """内存模式：清理过期记录"""
    now = time.time()
    cutoff = now - window
    timestamps = _mem_buckets.get(key, [])
    _mem_buckets[key] = [ts for ts in timestamps if ts > cutoff]


def rate_limit(max_requests: int = 10, window_seconds: int = 60) -> Callable:
    """返回 FastAPI 依赖，基于 Redis 滑动窗口限流（降级内存）"""

    def _checker(request: Request) -> None:
        if max_requests <= 0:
            return
        # 测试环境自动关闭
        if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("CG_DISABLE_RATE_LIMIT"):
            return

        ip = _get_client_ip(request)
        key = f"rl:{ip}:{request.method}:{request.url.path}"

        # Redis 滑动窗口
        if is_redis_available():
            r = get_redis()
            import time as _time
            now = _time.time()
            pipe = r.pipeline()
            pipe.zremrangebyscore(key, 0, now - window_seconds)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, window_seconds)
            results = pipe.execute()
            count = results[2]
            if count > max_requests:
                raise HTTPException(
                    status_code=429,
                    detail=f"请求过于频繁，请在 {window_seconds} 秒后再试",
                )
            return

        # 内存降级
        _mem_clean_bucket(key, window_seconds)
        if len(_mem_buckets.get(key, [])) >= max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"请求过于频繁，请在 {window_seconds} 秒后再试",
            )
        _mem_buckets.setdefault(key, []).append(time.time())

    return Depends(_checker)
