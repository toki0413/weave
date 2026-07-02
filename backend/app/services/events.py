"""事件广播服务

生产环境通过 Redis Pub/Sub 实现跨实例广播，
无 Redis 时降级到内存队列（仅单实例有效）。
"""
import asyncio
import json
import logging
import threading

from app.redis_client import get_redis, is_redis_available

logger = logging.getLogger("cognitive_garden")

# 内存模式：本实例 SSE 客户端队列
_event_queues: list = []

# Redis Pub/Sub 频道名
_CHANNEL = "cognitive_garden:events"

# Redis 订阅线程（懒启动）
_subscriber_started = False


def broadcast_event(data: dict):
    """广播事件到所有 SSE 客户端

    Redis 可用时：发布到频道，所有实例的订阅线程都会收到
    Redis 不可用：直接推到本实例内存队列
    """
    msg = json.dumps(data, ensure_ascii=False)

    if is_redis_available():
        try:
            r = get_redis()
            r.publish(_CHANNEL, msg)
            return
        except Exception as e:
            logger.warning("Redis 发布失败，降级内存: %s", e)

    # 内存降级
    _push_to_local_queues(msg)


def _push_to_local_queues(msg: str):
    """推送到本实例所有 SSE 队列"""
    dead = []
    for q in _event_queues:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try:
            _event_queues.remove(q)
        except ValueError:
            pass


def _ensure_subscriber():
    """启动 Redis 订阅线程（只启动一次）"""
    global _subscriber_started
    if _subscriber_started or not is_redis_available():
        return
    _subscriber_started = True

    def _listen():
        try:
            r = get_redis()
            pubsub = r.pubsub()
            pubsub.subscribe(_CHANNEL)
            for msg in pubsub.listen():
                if msg["type"] == "message":
                    _push_to_local_queues(msg["data"])
        except Exception as e:
            logger.error("Redis 订阅线程异常: %s", e)
            _subscriber_started = False

    t = threading.Thread(target=_listen, daemon=True, name="redis-subscriber")
    t.start()
    logger.info("Redis 事件订阅线程已启动")


def add_event_queue(q):
    """注册新的 SSE 客户端队列"""
    _event_queues.append(q)
    _ensure_subscriber()


def remove_event_queue(q):
    """移除 SSE 客户端队列"""
    try:
        _event_queues.remove(q)
    except ValueError:
        pass
