"""notification resolution columns (closed-loop alert feedback)

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-20 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "notifications",
        sa.Column("resolution_status", sa.String(20), nullable=True, server_default="pending"),
    )
    op.add_column("notifications", sa.Column("resolution_note", sa.Text, nullable=True))
    op.add_column("notifications", sa.Column("resolved_at", sa.DateTime, nullable=True))
    # 历史行补默认值
    op.execute("UPDATE notifications SET resolution_status = 'pending' WHERE resolution_status IS NULL")


def downgrade():
    op.drop_column("notifications", "resolved_at")
    op.drop_column("notifications", "resolution_note")
    op.drop_column("notifications", "resolution_status")
