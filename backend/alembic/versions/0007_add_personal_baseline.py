"""add personal baseline fields to baselines

Revision ID: 0007
Revises: 0006
Create Date: 2025-06-24 00:00:00

给 baselines 表增加 personal_mean、personal_std、sample_count，
用于存储用户自适应个人基线的均值、标准差与样本量。
"""
from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "baselines",
        sa.Column("personal_mean", sa.JSON(), nullable=True),
    )
    op.add_column(
        "baselines",
        sa.Column("personal_std", sa.JSON(), nullable=True),
    )
    op.add_column(
        "baselines",
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade():
    op.drop_column("baselines", "sample_count")
    op.drop_column("baselines", "personal_std")
    op.drop_column("baselines", "personal_mean")
