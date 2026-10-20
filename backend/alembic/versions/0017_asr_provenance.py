"""sessions ASR provenance columns (pilot data contract)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-20 00:00:00

四列一律可空、不给默认值。理由：Vosk 路径下没有真实置信度
（routers/stt.py 里 vosk 返回硬编码 0.9、google 硬编码 1.0），
若把 low_confidence 默认成 False，就等于替全部历史数据作保"转写可信"，
而 baseline_personal 之后要按这一列排除会话 —— 那个默认值会变成沉默的错误。
存量记录留 NULL，表示"未知"，排除逻辑只认真正的 True。
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("sessions") as batch:      # SQLite 需要 batch 模式
        batch.add_column(sa.Column("asr_provider", sa.String(20), nullable=True))
        batch.add_column(sa.Column("asr_confidence", sa.Float, nullable=True))
        batch.add_column(sa.Column("low_confidence", sa.Boolean, nullable=True))
        batch.add_column(sa.Column("asr_duration_sec", sa.Float, nullable=True))
        # 试点导出脚本按用户取时间序，避免全表扫
        batch.create_index("ix_sessions_user_created", ["user_id", "created_at"])


def downgrade():
    with op.batch_alter_table("sessions") as batch:
        batch.drop_index("ix_sessions_user_created")
        batch.drop_column("asr_duration_sec")
        batch.drop_column("low_confidence")
        batch.drop_column("asr_confidence")
        batch.drop_column("asr_provider")
