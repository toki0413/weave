"""在子进程里跑 alembic upgrade，返回 CompletedProcess。

为什么要子进程：alembic/env.py 用 get_settings().database_url 决定连接，
而 get_settings 带 lru_cache —— 它在 conftest 导入 app.database 时就已缓存成
默认值 sqlite:///./cognitive_garden.db。monkeypatch 改环境变量对**已缓存的
settings 无效**，实测 upgrade 打到了仓库工作目录里的开发库上。

子进程从零导入，环境变量必然生效；runner 内部还会断言 env.py 用的确实是
调用方给的临时库，打偏就失败，不会静默改到别的数据库。
"""
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def run_upgrade(db_file, ini, script_location):
    """用 `-m tests._alembic_runner` 而不是 `-c`：后者把 sys.path[0] 设成 cwd，
    子进程里 import 不到本模块（第一次就踩了 ModuleNotFoundError）。"""
    return subprocess.run(
        [sys.executable, "-m", "tests._alembic_runner",
         str(ini), str(script_location), str(db_file)],
        cwd=str(BACKEND), capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONPATH": str(BACKEND)},
    )


def _main(argv):
    ini, script_location, db_path = argv
    # 必须在这里重新读一遍 env，作为"URL 到底落到哪"的自证
    from alembic import command
    from alembic.config import Config
    from app.config import get_settings

    expected = str(db_path).replace("\\", "/")
    actual = get_settings().database_url.replace("\\", "/")
    print(f"SETTINGS_URL={actual}", file=sys.stderr)
    print(f"TARGET={expected}", file=sys.stderr)
    if expected not in actual:
        print("ABORT: env.py 的 URL 不是调用方给的临时库，拒绝执行", file=sys.stderr)
        return 3

    cfg = Config(ini)
    cfg.set_main_option("script_location", script_location)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{expected}")
    command.upgrade(cfg, "head")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
