"""add encrypted_payload to voice_messages

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('voice_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('encrypted_payload', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('voice_messages', schema=None) as batch_op:
        batch_op.drop_column('encrypted_payload')
