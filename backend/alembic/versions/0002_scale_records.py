"""add scale_records table

Revision ID: 0002
Revises: 0001
Create Date: 2025-06-23 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "scale_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scale_type", sa.String(20), nullable=False),
        sa.Column("answers", sa.JSON),
        sa.Column("total_score", sa.Integer, nullable=False),
        sa.Column("interpretation", sa.String(50)),
        sa.Column("created_at", sa.DateTime, default=sa.func.now()),
    )


def downgrade():
    op.drop_table("scale_records")
