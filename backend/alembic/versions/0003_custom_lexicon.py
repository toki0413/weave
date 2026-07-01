"""add custom_lexicon table

Revision ID: 0003
Revises: 0002
Create Date: 2025-06-23 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "custom_lexicon",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("word", sa.String(100), nullable=False),
        sa.Column("word_type", sa.Enum("person", "place", "event", "item", name="lexicon_word_type"), nullable=False),
        sa.Column("created_at", sa.DateTime, default=sa.func.now()),
    )
    op.create_index(
        "ix_custom_lexicon_user_id",
        "custom_lexicon",
        ["user_id"],
    )


def downgrade():
    op.drop_index("ix_custom_lexicon_user_id", table_name="custom_lexicon")
    op.drop_table("custom_lexicon")
