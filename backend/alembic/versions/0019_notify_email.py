"""users.notify_email：告警出站触达邮箱（gap 审计 G1）

家属填了 notify_email 才会收到邮件告警；不填只有应用内通知。
可空、无默认值：没有邮箱不该被填成空字符串再判空。

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-02 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:      # SQLite 需要 batch 模式
        batch.add_column(sa.Column("notify_email", sa.String(255), nullable=True))


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_column("notify_email")
