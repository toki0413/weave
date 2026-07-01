"""initial schema

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("phone", sa.String(20), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("elderly", "family", "doctor", "admin", name="user_role"), default="elderly"),
        sa.Column("name", sa.String(100)),
        sa.Column("created_at", sa.DateTime, default=sa.func.now()),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("day_number", sa.Integer, default=1),
        sa.Column("narrative", sa.Text),
        sa.Column("graph", sa.JSON),
        sa.Column("metrics", sa.JSON),
        sa.Column("health_score", sa.Integer),
        sa.Column("anomalies", sa.JSON),
        sa.Column("created_at", sa.DateTime, default=sa.func.now()),
    )

    op.create_table(
        "baselines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.id")),
        sa.Column("metrics", sa.JSON),
        sa.Column("created_at", sa.DateTime, default=sa.func.now()),
    )

    op.create_table(
        "user_states",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("nodes", sa.JSON, default=list),
        sa.Column("edges", sa.JSON, default=list),
        sa.Column("node_id_counter", sa.Integer, default=0),
        sa.Column("current_day", sa.Integer, default=0),
        sa.Column("day_snapshots", sa.JSON, default=dict),
        sa.Column("baseline_metrics", sa.JSON, nullable=True),
        sa.Column("welcome_dismissed", sa.Integer, default=0),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now()),
    )


def downgrade():
    op.drop_table("user_states")
    op.drop_table("baselines")
    op.drop_table("sessions")
    op.drop_table("users")
