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
    """获取客户端 IP。

    仅当 CG_TRUST_PROXY=1（前置反代可信）时才采信转发头，否则客户端
    自带 X-Forwarded-For 即可无限换 IP 绕过限流。
    可信模式下优先 X-Real-IP（由反代覆盖写入），其次取 XFF 最后一项
    （由最近一跳反代追加，客户端伪造值只可能出现在左侧）。
    """
    from app.config import get_settings
    if get_settings().trust_proxy:
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[-1].strip()
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
            from uuid import uuid4
            now = _time.time()
            # member 必须唯一：用纯时间戳作 member 时，同一毫秒内的并发
            # 请求会互相覆盖，窗口内计数偏小，限流被绕过。
            member = f"{now:.6f}-{uuid4().hex[:8]}"
            pipe = r.pipeline()
            pipe.zremrangebyscore(key, 0, now - window_seconds)
            pipe.zadd(key, {member: now})
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
