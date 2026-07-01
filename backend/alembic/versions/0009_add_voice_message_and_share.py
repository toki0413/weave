"""add voice_message and share_record tables

Revision ID: 0009
Revises: 0008
Create Date: 2025-06-23 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    # 语音留言表
    op.create_table(
        "voice_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sender_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("receiver_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("audio_url", sa.String(500), nullable=False),
        sa.Column("duration", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime, default=sa.func.now()),
        sa.Column("is_read", sa.Boolean, default=False),
    )
    op.create_index("ix_voice_messages_receiver_id", "voice_messages", ["receiver_id"])
    op.create_index("ix_voice_messages_sender_id", "voice_messages", ["sender_id"])

    # 分享记录表
    op.create_table(
        "share_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("elderly_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("family_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("shared_at", sa.DateTime, default=sa.func.now()),
        sa.Column("message", sa.Text, nullable=True),
    )
    op.create_index("ix_share_records_elderly_id", "share_records", ["elderly_id"])
    op.create_index("ix_share_records_family_id", "share_records", ["family_id"])
    op.create_index("ix_share_records_session_id", "share_records", ["session_id"])


def downgrade():
    op.drop_index("ix_share_records_session_id", table_name="share_records")
    op.drop_index("ix_share_records_family_id", table_name="share_records")
    op.drop_index("ix_share_records_elderly_id", table_name="share_records")
    op.drop_table("share_records")

    op.drop_index("ix_voice_messages_sender_id", table_name="voice_messages")
    op.drop_index("ix_voice_messages_receiver_id", table_name="voice_messages")
    op.drop_table("voice_messages")
