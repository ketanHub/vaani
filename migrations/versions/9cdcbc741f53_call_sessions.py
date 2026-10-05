"""call_sessions

Revision ID: 9cdcbc741f53
Revises: 9658d8402543
Create Date: 2026-10-03 15:57:33.906225
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9cdcbc741f53"
down_revision: str | Sequence[str] | None = "9658d8402543"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "call_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("call_id", sa.String(length=128), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "call_id",
            name="uq_call_session_tenant_call",
        ),
    )
    op.create_index(
        op.f("ix_call_sessions_call_id"),
        "call_sessions",
        ["call_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_call_sessions_channel"),
        "call_sessions",
        ["channel"],
        unique=False,
    )
    op.create_index(
        op.f("ix_call_sessions_tenant_id"),
        "call_sessions",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_call_sessions_tenant_id"),
        table_name="call_sessions",
    )
    op.drop_index(
        op.f("ix_call_sessions_channel"),
        table_name="call_sessions",
    )
    op.drop_index(
        op.f("ix_call_sessions_call_id"),
        table_name="call_sessions",
    )
    op.drop_table("call_sessions")
