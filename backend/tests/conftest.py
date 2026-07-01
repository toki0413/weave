"""pytest 公共 fixtures"""
import os

# 强制使用内存数据库，避免 main.py 导入时操作真实文件数据库
os.environ["database_url"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, get_db, engine
from app.main import app


def _override_get_db():
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 把全局 get_db 换成测试库
app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def clean_db():
    """每个测试前重建表结构，保证互不干扰"""
    from app.services import key_manager
    key_manager.clear_all()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    key_manager.clear_all()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    """直接拿到 SQLAlchemy 会话，用于绕过 API 直接造数据"""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def auth_headers(client):
    """注册并登录一个测试用户，返回 token 和带 Authorization 的 headers"""
    phone = "13800000000"
    password = "Test123456!"
    r = client.post("/api/v1/auth/register", json={
        "phone": phone,
        "password": password,
        "name": "测试用户",
    })
    assert r.status_code == 200, f"注册失败: {r.text}"
    # 再走一次登录，确认凭据可用
    r = client.post("/api/v1/auth/login", json={"phone": phone, "password": password})
    assert r.status_code == 200, f"登录失败: {r.text}"
    token = r.json()["access_token"]
    return {"token": token, "headers": {"Authorization": f"Bearer {token}"}}
