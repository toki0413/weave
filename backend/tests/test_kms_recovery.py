"""KMS 恢复路径（gap 审计 G3）测试

覆盖：FileKMS 导出/导入 roundtrip（真实灾后恢复语义）、坏密钥校验、
describe 状态、路由层 admin 门禁与 env provider 的 409 语义。
"""
import base64

import pytest

from app.services import kms


@pytest.fixture
def kms_tmp_home(tmp_path, monkeypatch):
    """FileKMS 密钥目录指到临时目录，隔离测试与真实环境（防覆盖真机密钥）"""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    old = kms._provider
    kms._provider = None
    yield tmp_path
    kms._provider = old


def _register(client, username, role="elderly"):
    """注册用户并返回鉴权头。

    权限提升角色走"运维在库里改 role"的路径：自助注册接口只接受
    elderly / family，admin 必须由管理侧开通（见 auth.register）。
    """
    r = client.post("/api/v1/auth/register", json={
        "username": username,
        "password": "Test123456!",
        "name": username,
        "role": "elderly",
    })
    assert r.status_code == 200, r.text
    if role != "elderly":
        from app.database import SessionLocal
        from app.models import User
        db = SessionLocal()
        try:
            db.query(User).filter(User.username == username).update({"role": role})
            db.commit()
        finally:
            db.close()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _break_wrap_key(tmp_path):
    """模拟灾难：删掉密钥文件并重置单例，新 provider 会生成一把不同的密钥"""
    (tmp_path / ".cognitive-garden" / "kms_wrap_key.bin").unlink()
    kms._provider = None
    return kms.init_kms()


# ---------- 服务层 ----------

def test_file_kms_export_import_roundtrip(kms_tmp_home):
    p = kms.init_kms()
    plaintext, encrypted = p.generate_data_key()

    exported = kms.export_wrap_key()
    assert base64.b64decode(exported) == p._key

    # 灾后：wrap key 丢失，新密钥解不开历史数据
    _break_wrap_key(kms_tmp_home)
    with pytest.raises(Exception):
        kms.unwrap_master_key(encrypted)

    # 恢复备份后立即可解，无需重启
    kms.import_wrap_key(exported)
    assert kms.unwrap_master_key(encrypted) == plaintext


def test_import_rejects_bad_key(kms_tmp_home):
    kms.init_kms()
    with pytest.raises(ValueError):
        kms.import_wrap_key("not-base64!!!")
    with pytest.raises(ValueError):
        kms.import_wrap_key(base64.b64encode(b"short").decode())


def test_describe_kms_file_provider(kms_tmp_home):
    kms.init_kms()
    info = kms.describe_kms()
    assert info["provider"] == "FileKMS"
    assert info["exportable"] is True
    assert str(kms_tmp_home) in info["key_file"]
    assert info["key_file_exists"] is True


def test_env_provider_rejects_export_import():
    old = kms._provider
    kms._provider = kms.EnvKMS(base64.b64encode(b"k" * 32).decode())
    try:
        with pytest.raises(ValueError):
            kms.export_wrap_key()
        with pytest.raises(ValueError):
            kms.import_wrap_key(base64.b64encode(b"k" * 32).decode())
        info = kms.describe_kms()
        assert info["exportable"] is False
        assert "CG_KMS_MASTER_KEY" in info["message"]
    finally:
        kms._provider = old


# ---------- 路由层 ----------

def test_kms_endpoints_admin_only(client, kms_tmp_home):
    family_headers = _register(client, "kms_family", "family")
    for path in ("/api/v1/backup/kms-status", "/api/v1/backup/kms-wrap-key"):
        assert client.get(path, headers=family_headers).status_code == 403
    assert client.post(
        "/api/v1/backup/kms-wrap-key",
        json={"key_b64": base64.b64encode(b"k" * 32).decode()},
        headers=family_headers,
    ).status_code == 403


def test_kms_export_import_via_api(client, kms_tmp_home):
    admin_headers = _register(client, "kms_admin", "admin")

    # 先造一条"灾前"数据密钥
    p = kms.init_kms()
    plaintext, encrypted = p.generate_data_key()

    r = client.get("/api/v1/backup/kms-status", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["exportable"] is True

    r = client.get("/api/v1/backup/kms-wrap-key", headers=admin_headers)
    assert r.status_code == 200
    exported = r.json()["key_b64"]

    # 灾难 → 恢复
    _break_wrap_key(kms_tmp_home)
    r = client.post(
        "/api/v1/backup/kms-wrap-key",
        json={"key_b64": exported},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert kms.unwrap_master_key(encrypted) == plaintext


def test_kms_import_rejects_bad_key_via_api(client, kms_tmp_home):
    admin_headers = _register(client, "kms_admin2", "admin")
    kms.init_kms()
    r = client.post(
        "/api/v1/backup/kms-wrap-key",
        json={"key_b64": "short-key"},
        headers=admin_headers,
    )
    assert r.status_code == 400
