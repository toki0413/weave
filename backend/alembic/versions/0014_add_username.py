"""add username column, make phone optional

Revision ID: 0014
Revises: 0013
Create Date: 2026-01-01 00:00:00

原文件在仓库里是 68 字节的截断残檔（末行停在 "Revis"、docstring 三引号只出现
一次），alembic 的 ScriptDirectory 加载整个 versions/ 时直接抛 SyntaxError，
导致任何 `alembic upgrade` 都跑不到 head —— 新库靠 main.py 的 create_all 降级
侥幸能用，存量库则永远拿不到后续列（0017 的 ASR 溯源列就是这种情况）。

本文件按 **no-op 占位** 重建，不是照原意重做 DDL，理由：
app/models.py 里 User.username 与 phone(nullable=True) 早已是最终形态，
现存库都是从那份 models 建出来的（create_all 或既有 dump），这两项变更在
所有实际存在的库里都已经生效。重做 ALTER 反而会在 SQLite 上撞 already exists。

代价：若真有某个库停在 0013 之前、缺 username 列，它升级后仍会缺列。
这种库应当由 tests/test_weekly_baseline.py 的 schema 自检暴露，而不是靠这条
迁移兜住 —— 已另加一条断言 username 列存在的回归。

后续维护：如果将来要真正对齐 0013→0014 的 DDL，请把本文件的 upgrade() 补上，
并同步把 tests/test_p1_asr_provenance.py::
test_upstream_0014_is_truncated_known_defect 反转成结构守护。
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
