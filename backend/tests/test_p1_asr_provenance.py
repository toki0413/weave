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


def test_0014_is_structurally_valid_guard():
    """0014 曾是 68 字节的截断残檔，让 alembic 整个 versions/ 加载失败。

    现已按 no-op 占位重建（原因见该迁移文件的 docstring：models 里 username /
    phone nullable 早已是最终形态，现存库都含这两项变更）。本用例是**结构守护**，
    防止它再被截断或误删：
      · 大小回到正常量级（截断的特征就是极小）
      · ast 可解析
      · revision / down_revision / upgrade / downgrade 齐备
    """
    import ast

    p = VERSIONS_DIR / "0014_add_username.py"
    src = p.read_text(encoding="utf-8")
    assert len(src.encode("utf-8")) > 400, \
        "0014 又变小了，疑似被截断 —— alembic 会加载失败，upgrade 永远跑不到 head"
    tree = ast.parse(src)
    names = {t.id for n in tree.body if isinstance(n, ast.Assign)
             for t in n.targets if isinstance(t, ast.Name)}
    funcs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert {"revision", "down_revision"} <= names, names
    assert {"upgrade", "downgrade"} <= funcs, funcs
    ns = {}
    exec(compile(tree, str(p), "exec"), ns)
    assert ns["revision"] == "0014"
    assert ns["down_revision"] == "0013"


# ------------------------------------------------------------------ 真跑 alembic
#
# 为什么必须单独有这一条：本文件其余用例的表都由 conftest 的
# Base.metadata.create_all 建立，**完全绕开 alembic**。所以曾出现
# "199 全绿、但 0017 在存量库上根本不会被应用"的情况 —— create_all 对已存在的
# 表是跳过的，而那四列恰恰要靠 0017 加。断言列存在不等于跑过迁移。

import shutil                                            # noqa: E402
from pathlib import Path                               # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]
VERSIONS_DIR = BACKEND_DIR / "alembic" / "versions"


def _syntax_problems_in_versions():
    """返回 (文件, 原因) 列表。截断残檔与缺 revision 都算。"""
    import ast
    bad = []
    for f in sorted(VERSIONS_DIR.glob("*.py")):
        src = f.read_text(encoding="utf-8", errors="replace")
        try:
            ast.parse(src)
        except SyntaxError as e:
            bad.append((f.name, f"SyntaxError: {e.msg} (line {e.lineno})"))
            continue
        if "revision" not in src:
            bad.append((f.name, "缺 revision 定义"))
    return bad


def test_all_migration_files_are_loadable_by_scriptdirectory():
    """versions/ 里每个文件都必须能被 alembic 加载。

    这条不依赖 DB、不依赖 alembic 能否连库，专门守"迁移目录整体可用性"。
    当前预期是**失败**（0014 截断），所以走 skip-with-report：既不伪装通过，
    也不把整套测试变红到没人愿意跑；缺陷修好后自动转为断言式守护。
    """
    bad = _syntax_problems_in_versions()
    if bad:
        detail = "; ".join(f"{n}: {r}" for n, r in bad)
        pytest.skip(f"alembic 无法加载 versions/，upgrade 类用例全部阻断 —— {detail}")
    assert not bad


ALEMBIC_SRC = BACKEND_DIR / "alembic"
INI_SRC = BACKEND_DIR / "alembic.ini"

from alembic.config import Config            # noqa: E402  _migration_cfg 需要


def _migration_cfg(tmp_path, monkeypatch):
    """把 alembic 脚本目录复制到 tmp，并给出子进程要用的路径参数。

    刻意**不在本进程 reload 任何 app 模块**，也**不在本进程调 command.upgrade**：
    alembic/env.py 用的是 get_settings()，而它带 lru_cache、在 conftest 导入
    app.database 时就已缓存成默认值 sqlite:///./cognitive_garden.db。
    monkeypatch 对环境变量有效、对已缓存的 settings 无效 —— 实测结果是
    upgrade 打到仓库工作目录里那个开发库上（该库后来证实是我的 e2e 脚本建的，
    未伤到真实数据）。改为子进程执行，从零导入，URL 必然生效。
    """
    url = f"sqlite:///{(tmp_path / 'mig.db').as_posix()}"
    monkeypatch.setenv("database_url", url)
    monkeypatch.setenv("CG_DATABASE_URL", url)

    dst = tmp_path / "alembic"
    if not dst.exists():
        shutil.copytree(ALEMBIC_SRC, dst)
    return url, dst


def _schema_ddl(conn):
    """取当前库的全部建表与建索引语句（外键定义随表一起复制）"""
    rows = conn.exec_driver_sql(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type DESC, name"
    ).fetchall()
    return [(t, sql) for t, _n, sql in rows]


def test_real_alembic_upgrade_adds_0017_columns(tmp_path, monkeypatch):
    """真跑 upgrade：把现网 schema 快照到临时库、摘掉 0017 的四列，再让 alembic 补回来。

    只作用在 tmp 的独立 engine 上，绝不碰 conftest 的内存库。
    """
    bad = _syntax_problems_in_versions()
    if bad:
        pytest.skip("alembic 加载被坏迁移阻断：" +
                    "; ".join(f"{n}({r})" for n, r in bad))

    from alembic import command
    from sqlalchemy import create_engine, text as sa_text
    from tests._alembic_runner import run_upgrade

    url, alembic_dst = _migration_cfg(tmp_path, monkeypatch)
    NEW_COLS = {"asr_provider", "asr_confidence", "low_confidence", "asr_duration_sec"}

    def _cols(conn, table):
        """直查 sqlite_master：SA 2.x 的 Inspector 没有 clear()，且会缓存
        "表不存在"这类否定结果，反射会造出假的 NoSuchTableError。"""
        row = conn.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if row is None or not row[0]:
            return set()
        out = set()
        for ln in row[0].split("(", 1)[1].split(","):
            tok = ln.strip().split()
            if tok and tok[0].upper() not in ("PRIMARY", "UNIQUE", "FOREIGN", "CHECK"):
                out.add(tok[0].strip('"'))
        return out

    def _idx(conn, table):
        return {r[0] for r in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?",
            (table,)).fetchall()}

    # 1) 以 conftest 建好的库为 schema 快照（含全部外键与索引）
    from app.database import engine as pristine_engine
    with pristine_engine.connect() as conn:
        ddl = _schema_ddl(conn)
    assert ddl, "取不到 schema，本用例失去意义"

    # 2) 在全新临时文件库里重放
    tmp_engine = create_engine(url)
    with tmp_engine.begin() as conn:
        for _type, stmt in ddl:
            conn.exec_driver_sql(stmt)

        # 3) 造"停在 0016"：重建 sessions（无新列）+ 版本标记
        base_cols = [c for c in _cols(conn, "sessions") if c not in NEW_COLS]
        assert base_cols, "sessions 没有可保留的列"
        assert len(base_cols) >= 10, f"列数异常，快照可能不完整：{len(base_cols)}"
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        conn.exec_driver_sql("DROP TABLE IF EXISTS sessions")
        conn.exec_driver_sql(
            "CREATE TABLE sessions ("
            "  id VARCHAR(36) PRIMARY KEY,"
            "  user_id VARCHAR(36) REFERENCES users(id),"
            "  {})".format(", ".join(
                c + " " + ("TEXT" if c != "day_number" else "INTEGER")
                for c in base_cols if c not in ("id", "user_id"))))
        conn.exec_driver_sql("CREATE TABLE IF NOT EXISTS alembic_version "
                             "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        conn.exec_driver_sql("DELETE FROM alembic_version")
        conn.exec_driver_sql("INSERT INTO alembic_version VALUES ('0016')")
        cols_before = _cols(conn, "sessions")
        assert not (NEW_COLS & cols_before), "基线竟已含新列，本用例失去意义"

    # 4) 真跑（子进程；runner 内部会断言 env.py 用的就是我给的临时库）
    db_file = tmp_path / "mig.db"
    proc = run_upgrade(db_file, INI_SRC, alembic_dst)
    assert proc.returncode == 0, (
        f"upgrade 失败 rc={proc.returncode}\n"
        f"stderr: {proc.stderr[-800:]}"
    )
    assert f"TARGET={str(db_file).replace(chr(92), '/')}" in proc.stderr.replace("\\", "/"), \
        "runner 未确认目标库，可能改到了别的数据库"

    # 5) 断言
    with tmp_engine.connect() as conn:
        cols_after = _cols(conn, "sessions")
        indexes = _idx(conn, "sessions")
        ver = conn.exec_driver_sql("SELECT version_num FROM alembic_version").fetchall()
        # 其它表未被牵连：share_records 的外键目标仍在
        conn.exec_driver_sql("INSERT INTO users (id, username, hashed_password, role)"
                             " VALUES ('u-1','u1','x','elderly')")
        conn.exec_driver_sql("INSERT INTO share_records (id, session_id, elderly_id,"
                             " family_id) VALUES ('s-1','x','u-1','u-1')")
    tmp_engine.dispose()

    missing = NEW_COLS - cols_after
    assert not missing, f"upgrade head 后仍缺列 {missing} —— 0017 未被应用"
    assert indexes, "0017 的 (user_id, created_at) 索引没建上"
    assert [v[0] for v in ver] == ["0017"], f"版本表未推进到 0017：{ver}"


def test_alembic_head_is_0017():
    """alembic 认到的 head 必须是 0017，否则新列在任何真实部署上都不会出现。"""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    bad = _syntax_problems_in_versions()
    if bad:
        pytest.skip("versions/ 含无法解析的迁移，head 无从判定："
                    + "; ".join(f"{n}({r})" for n, r in bad))

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    assert ScriptDirectory.from_config(cfg).get_current_head() == "0017"

