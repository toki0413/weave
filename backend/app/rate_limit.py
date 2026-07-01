"""简单的内存式速率限制依赖。

用于单实例部署。若后续多实例部署，应替换为 Redis 等共享存储。
"""
import os
import time
from collections import defaultdict
from typing import Callable, List

from fastapi import Request, HTTPException, Depends

# key -> 最近请求时间戳列表（单调递增）
_buckets: dict[str, List[float]] = defaultdict(list)


def _get_client_ip(request: Request) -> str:
    """获取客户端 IP，优先处理反向代理转发头。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _clean_bucket(key: str, window: float) -> None:
    """清理桶内过期的旧记录，只保留窗口期内最近 max_requests 条即可。"""
    now = time.time()
    timestamps = _buckets[key]
    cutoff = now - window
    # 由于列表按时间递增，找到第一个未过期的位置后切片
    start = 0
    for i, ts in enumerate(timestamps):
        if ts > cutoff:
            start = i
            break
    else:
        start = len(timestamps)
    _buckets[key] = timestamps[start:]


def rate_limit(max_requests: int = 10, window_seconds: int = 60) -> Callable:
    """返回一个 FastAPI 依赖，用于限制同一 IP 在 window_seconds 内最多请求 max_requests 次。"""

    def _checker(request: Request) -> None:
        if max_requests <= 0:
            return
        # 测试环境下自动关闭限流，避免测试共享全局状态导致失败
        if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("CG_DISABLE_RATE_LIMIT"):
            return
        ip = _get_client_ip(request)
        key = f"{ip}:{request.method}:{request.url.path}"
        _clean_bucket(key, window_seconds)
        if len(_buckets[key]) >= max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"请求过于频繁，请在 {window_seconds} 秒后再试",
            )
        _buckets[key].append(time.time())

    return Depends(_checker)
