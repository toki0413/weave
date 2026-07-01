"""add temporal_references to sessions

Revision ID: 0008
Revises: 0007
Create Date: 2025-06-24 00:00:00

给 sessions 表增加 temporal_references（JSON，nullable），
用于存储 NLP 时间实体解析结果，支持自动调整 day_number。
"""
from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "sessions",
        sa.Column("temporal_references", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("sessions", "temporal_references")
