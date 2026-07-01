"""用户加密密钥的内存缓存

密钥只在用户登录会话期间存在，进程重启或登出后即消失。
用线程锁保护，避免并发写入丢失。

新架构：同时缓存 KEK（密码派生密钥）和 master_key（随机主密钥）。
业务数据由 master_key 加密；KEK 仅用于包装/解包 master_key。
"""
import threading

_lock = threading.Lock()
_keys: dict = {}  # {user_id: {"kek": bytes, "master_key": bytes}}


def set_user_keys(user_id: str, kek: bytes, master_key: bytes) -> None:
    """登录成功后缓存用户的 KEK 和主密钥"""
    with _lock:
        _keys[user_id] = {"kek": kek, "master_key": master_key}


def set_user_key(user_id: str, key: bytes) -> None:
    """兼容旧接口：仅设置 KEK（调用方应尽快补充 master_key）"""
    with _lock:
        existing = _keys.get(user_id, {})
        existing["kek"] = key
        _keys[user_id] = existing


def get_user_key(user_id: str) -> bytes:
    """获取当前用户的业务加密主密钥，没有则抛错"""
    with _lock:
        record = _keys.get(user_id)
    if record is None or record.get("master_key") is None:
        raise RuntimeError("加密密钥不可用，请重新登录")
    return record["master_key"]


def get_user_kek(user_id: str) -> bytes:
    """获取当前用户的 KEK（用于修改密码时重新包装主密钥）"""
    with _lock:
        record = _keys.get(user_id)
    if record is None or record.get("kek") is None:
        raise RuntimeError("加密密钥不可用，请重新登录")
    return record["kek"]


def has_user_key(user_id: str) -> bool:
    """检查用户主密钥是否已缓存"""
    with _lock:
        record = _keys.get(user_id)
        return record is not None and record.get("master_key") is not None


def has_user_kek(user_id: str) -> bool:
    """检查用户 KEK 是否已缓存"""
    with _lock:
        record = _keys.get(user_id)
        return record is not None and record.get("kek") is not None


def clear_user_key(user_id: str) -> None:
    """登出时清除密钥"""
    with _lock:
        _keys.pop(user_id, None)


def clear_all() -> None:
    """清空全部缓存（测试或关闭时用）"""
    with _lock:
        _keys.clear()
