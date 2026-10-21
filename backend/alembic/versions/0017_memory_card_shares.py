"""add memory_card_shares table (K-factor share loop)"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_card_shares",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("family_user_id", sa.String(36),
                  sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("elderly_user_id", sa.String(36),
                  sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("week_start", sa.DateTime(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_table("memory_card_shares")
