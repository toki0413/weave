"""应用生命周期：后台任务必须随启动拉起、随关闭清理

旧实现用 `@app.on_event("startup")`，只启动不停止。进程退出或热重载时
任务仍挂在事件循环上，asyncio 会打印 "Task was destroyed but it is
pending"，测试里反复进出应用也会累积。迁移到 lifespan 后由 finally 兜住。

同时确认弃用接口不再被使用——FastAPI 后续版本会移除 on_event。
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import missed_checkin_job as daily
from app.services import weekly_digest_job as weekly


@pytest.fixture(autouse=True)
def _reset_tasks():
    daily._task = None
    weekly._task = None
    yield
    daily._task = None
    weekly._task = None


def test_lifespan_starts_and_stops_background_jobs():
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert daily._task is not None and not daily._task.done(), (
            "漏录提醒任务未随启动拉起")
        assert weekly._task is not None and not weekly._task.done(), (
            "家属周摘要任务未随启动拉起")

    assert daily._task is None, "关闭后漏录提醒任务未清理"
    assert weekly._task is None, "关闭后家属周摘要任务未清理"


def test_lifespan_can_be_entered_twice():
    """热重载/多次启动不得因残留任务而报错或重复创建"""
    for _ in range(2):
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            assert daily._task is not None
        assert daily._task is None


def test_on_event_is_no_longer_used():
    """项目代码不得再注册 on_event（FastAPI 未来版本会移除）"""
    import inspect

    import app.main as main_mod

    source = inspect.getsource(main_mod)
    assert "on_event" not in source.replace(
        "替代已弃用的 @app.on_event", ""), "main.py 仍在注册 on_event 钩子"
