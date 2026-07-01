"""add family_link is_active, doctor_patient, device_sync tables

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add is_active to family_links
    with op.batch_alter_table('family_links', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=True))
    op.execute("UPDATE family_links SET is_active = 1")
    with op.batch_alter_table('family_links', schema=None) as batch_op:
        batch_op.alter_column('is_active', existing_type=sa.Boolean(), nullable=False)

    # 2) Create doctor_patients table
    # 外键直接内联到 Column，SQLite 不支持独立的 ADD CONSTRAINT
    op.create_table(
        'doctor_patients',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('doctor_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('patient_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('access_level', sa.String(20), nullable=False, server_default='read'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_doctor_patients_doctor_id', 'doctor_patients', ['doctor_id'])
    op.create_index('ix_doctor_patients_patient_id', 'doctor_patients', ['patient_id'])

    # 3) Create device_syncs table
    op.create_table(
        'device_syncs',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('device_id', sa.String(255), nullable=False),
        sa.Column('vector_clock', sa.JSON(), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'device_id'),
    )
    op.create_index('ix_device_syncs_user_id', 'device_syncs', ['user_id'])
    op.create_index('ix_device_syncs_device_id', 'device_syncs', ['device_id'])


def downgrade() -> None:
    op.drop_table('device_syncs')
    op.drop_table('doctor_patients')
    with op.batch_alter_table('family_links', schema=None) as batch_op:
        batch_op.drop_column('is_active')
