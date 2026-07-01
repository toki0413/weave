"""add notifications and family_links tables

Revision ID: 0004
Revises: 0003
Create Date: 2025-06-23 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    # 家属-老人绑定关系
    op.create_table(
        "family_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("elderly_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("family_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("relation", sa.String(50)),
        sa.Column("created_at", sa.DateTime, default=sa.func.now()),
    )
    op.create_index("ix_family_links_elderly_user_id", "family_links", ["elderly_user_id"])
    op.create_index("ix_family_links_family_user_id", "family_links", ["family_user_id"])

    # 家属端通知
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text),
        sa.Column("severity", sa.String(20), default="info"),
        sa.Column("related_data", sa.JSON),
        sa.Column("is_read", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime, default=sa.func.now()),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])


def downgrade():
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_family_links_family_user_id", table_name="family_links")
    op.drop_index("ix_family_links_elderly_user_id", table_name="family_links")
    op.drop_table("family_links")
