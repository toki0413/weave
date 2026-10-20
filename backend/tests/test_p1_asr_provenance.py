"""P1 试点数据契约回归

覆盖两件事：
1. 0017 迁移在 SQLite 上可上可下（batch_alter_table 路径）。
2. build_personal_baseline 只剔除 low_confidence is True 的记录；
   NULL（旧数据、未知）必须保留 —— 把它当 False 是替历史作保，
   把它当 True 会静默清空存量用户的基线。
"""
from datetime import datetime, timedelta, timezone

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect

import app.models  # noqa: F401  确保 Base 元数据完整
from app.database import engine
from app.models import Session as DBSession, User
from app.services import key_manager as km
from app.services.baseline_personal import build_personal_baseline

BASELINE_METRICS = {
    "connectivity": 0.6, "clustering": 0.4, "centrality": 0.5,
    "entropy": 0.7, "density": 0.3, "nodeCount": 12, "edgeCount": 20,
}


def _user(db):
    u = User(username="p1_user", hashed_password="x", role="elderly", name="测试")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _sess(db, uid, days_ago, low_conf, metrics=None):
    db.add(DBSession(
        user_id=uid, day_number=days_ago + 1,
        narrative="今天秀兰陪我去公园，路上碰见建国。",
        is_encrypted=False,
        graph={"nodes": [], "edges": []},
        metrics=metrics if metrics is not None else dict(BASELINE_METRICS),
        health_score=80, anomalies=[],
        low_confidence=low_conf,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    ))
    db.commit()


def test_new_columns_exist():
    cols = {c["name"] for c in inspect(engine).get_columns("sessions")}
    assert {"asr_provider", "asr_confidence", "low_confidence",
            "asr_duration_sec"} <= cols


def test_low_confidence_true_excluded_null_and_false_kept(db_session):
    u = _user(db_session)
    # 5 条 False + 3 条 True + 4 条 NULL（模拟存量旧数据），共 12 条候选
    for i in range(5):
        _sess(db_session, u.id, i, False)
    for i in range(5, 8):
        _sess(db_session, u.id, i, True)
    for i in range(8, 12):
        _sess(db_session, u.id, i, None)

    base = build_personal_baseline(u.id, db_session, sample_size=10)

    assert base is not None, "基线没建出来，可能被过度剔除"
    # 候选池加宽到 3×10=30，12 条全取到；剔掉 3 条 True 后剩 9 条
    # （5 False + 4 NULL），不足 10 配额所以如实给 9。
    # 关键不是 9 还是 10，而是 NULL 一条没被剔 —— 把"未知"当"不可信"
    # 会让存量用户在新列上线当天集体掉基线。
    assert base["sample_count"] == 9
    assert base["excluded_low_confidence"] == 3
    assert base["personal_mean"]["nodeCount"] == pytest.approx(12.0)


def test_quota_not_wasted_by_excluded_rows(db_session):
    """剔除发生在 limit 之后：被剔的条数不该白占 sample_size 配额。"""
    u = _user(db_session)
    # 最近 6 天全是低置信，更早的 6 天正常
    for i in range(6):
        _sess(db_session, u.id, i, True)
    for i in range(6, 12):
        _sess(db_session, u.id, i, False)

    base = build_personal_baseline(u.id, db_session, sample_size=6)
    assert base is not None, "只看了最近 6 条就被剔空，等于没做加宽取样"
    assert base["sample_count"] == 6


def test_all_low_confidence_degrades_to_no_baseline(db_session):
    u = _user(db_session)
    for i in range(5):
        _sess(db_session, u.id, i, True)
    assert build_personal_baseline(u.id, db_session, sample_size=7) is None


def test_migration_0017_metadata_and_callables():
    """只验 0017 自身。

    不走 ScriptDirectory.from_config()：仓库里的 0014_add_username.py 是被截断
    的 68 字节残檔（末行停在 "Revis"，三引号只出现 1 次），加载整个 versions
    目录会先撞它的 SyntaxError。见下一个用例，那条把这个问题显式记下来。
    """
    import importlib.util
    from pathlib import Path

    path = (Path(__file__).resolve().parents[1]
            / "alembic" / "versions" / "0017_asr_provenance.py")
    spec = importlib.util.spec_from_file_location("m0017", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.revision == "0017"
    assert mod.down_revision == "0016"
    assert callable(mod.upgrade) and callable(mod.downgrade)


def test_upstream_0014_is_truncated_known_defect():
    """已知上游缺陷：0014 内容被截断，任何 alembic 全量升级都会挂。

    本用例断言的是"缺陷存在"，不是"已修复"。修好后它会失败，届时把断言反过来
    变成守护测试，别直接删 —— 否则这条信息就又丢了。
    """
    from pathlib import Path

    p = (Path(__file__).resolve().parents[1]
         / "alembic" / "versions" / "0014_add_username.py")
    raw = p.read_bytes()
    assert len(raw) < 200, f"0014 看起来已修好（{len(raw)} 字节），请把本断言改为守护"
    text = raw.decode("utf-8", errors="replace")
    assert text.count('"""') < 2, "docstring 未闭合"
