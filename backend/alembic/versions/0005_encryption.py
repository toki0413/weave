"""add encryption fields

Revision ID: 0005
Revises: 0003
Create Date: 2025-06-23 00:00:00

给 users 加 encryption_salt（密码派生密钥用），给 sessions 和
scale_records 加 is_encrypted（标记是否已加密，兼容旧数据）。
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("encryption_salt", sa.String(64), nullable=True))
    op.add_column(
        "sessions",
        sa.Column("is_encrypted", sa.Boolean, nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "scale_records",
        sa.Column("is_encrypted", sa.Boolean, nullable=False, server_default=sa.text("0")),
    )


def downgrade():
    op.drop_column("scale_records", "is_encrypted")
    op.drop_column("sessions", "is_encrypted")
    op.drop_column("users", "encryption_salt")
