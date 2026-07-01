"""主密钥、恢复码相关测试"""
import pytest

from app.services.crypto import (
    derive_key,
    generate_master_key,
    wrap_master_key,
    unwrap_master_key,
)
from app.services import key_manager


SALT = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
PASSWORD = "test_password_123"


def test_generate_master_key_random():
    """每次生成的主密钥应不同，且长度为32字节"""
    k1 = generate_master_key()
    k2 = generate_master_key()
    assert len(k1) == 32
    assert k1 != k2


def test_wrap_unwrap_master_key():
    """主密钥经 KEK 包装后应能原样解出"""
    kek = derive_key(PASSWORD, SALT)
    master = generate_master_key()
    wrapped = wrap_master_key(master, kek)
    assert isinstance(wrapped, str)
    unwrapped = unwrap_master_key(wrapped, kek)
    assert unwrapped == master


def test_wrap_unwrap_with_wrong_kek_fails():
    """用错误 KEK 解包主密钥应失败"""
    kek = derive_key(PASSWORD, SALT)
    master = generate_master_key()
    wrapped = wrap_master_key(master, kek)
    wrong_kek = derive_key("wrong_password", SALT)
    with pytest.raises(Exception):
        unwrap_master_key(wrapped, wrong_kek)


def test_key_manager_kek_and_master_key():
    """缓存同时保存 KEK 和主密钥"""
    key_manager.clear_all()
    kek = derive_key(PASSWORD, SALT)
    master = generate_master_key()
    key_manager.set_user_keys("u1", kek, master)
    assert key_manager.get_user_key("u1") == master
    assert key_manager.get_user_kek("u1") == kek
    assert key_manager.has_user_key("u1") is True
    assert key_manager.has_user_kek("u1") is True


def test_key_manager_clear_keeps_nothing():
    """clear_user_key 应同时清除 KEK 和主密钥"""
    key_manager.set_user_keys("u2", b"kek", b"master")
    key_manager.clear_user_key("u2")
    assert key_manager.has_user_key("u2") is False
    assert key_manager.has_user_kek("u2") is False
    with pytest.raises(RuntimeError):
        key_manager.get_user_key("u2")
    with pytest.raises(RuntimeError):
        key_manager.get_user_kek("u2")
