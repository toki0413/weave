"""事件广播服务，避免与 main.py 的循环导入"""
import asyncio
import json

_event_queues = []


def broadcast_event(data: dict):
    """向所有 SSE 客户端广播事件（内部都是同步操作，无需 async）"""
    msg = json.dumps(data, ensure_ascii=False)
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


def add_event_queue(q):
    """注册新的 SSE 队列"""
    _event_queues.append(q)


def remove_event_queue(q):
    """移除 SSE 队列"""
    try:
        _event_queues.remove(q)
    except ValueError:
        pass
