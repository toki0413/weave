"""add master key and recovery fields

Revision ID: 0006
Revises: 0005
Create Date: 2025-06-23 00:00:00

给用户表增加 master_key_encrypted（经 KEK 加密的主密钥）和
recovery_code_hash（恢复码哈希），并新增 recovery_requests 表用于
家属/医生发起解密授权请求。
"""
from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("master_key_encrypted", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("recovery_code_hash", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("recovery_master_key_encrypted", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("recovery_salt", sa.String(64), nullable=True))

    op.create_table(
        "recovery_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("requester_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("recovery_requests")
    op.drop_column("users", "recovery_salt")
    op.drop_column("users", "recovery_master_key_encrypted")
    op.drop_column("users", "recovery_code_hash")
    op.drop_column("users", "master_key_encrypted")
