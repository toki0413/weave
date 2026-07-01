"""add emotion fields and training_records table

Revision ID: 0010
Revises: 0008
Create Date: 2025-06-25 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    # 给 sessions 表增加情感分析字段
    op.add_column("sessions", sa.Column("emotion_score", sa.Float(), nullable=True))
    op.add_column("sessions", sa.Column("emotion_label", sa.String(20), nullable=True))
    op.create_index("ix_sessions_emotion_label", "sessions", ["emotion_label"])

    # 训练游戏记录表
    op.create_table(
        "training_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("game_type", sa.String(50), nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("completed_at", sa.DateTime, default=sa.func.now()),
    )


def downgrade():
    op.drop_table("training_records")
    op.drop_index("ix_sessions_emotion_label", table_name="sessions")
    op.drop_column("sessions", "emotion_label")
    op.drop_column("sessions", "emotion_score")
