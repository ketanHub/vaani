"""turn_metrics

Revision ID: 9658d8402543
Revises: e26d7f5ddf5e
Create Date: 2026-10-03 15:51:51.321123
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9658d8402543"
down_revision: str | Sequence[str] | None = "e26d7f5ddf5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "turn_metrics",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("call_id", sa.String(length=128), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("grounded", sa.Boolean(), nullable=False),
        sa.Column("handoff_required", sa.Boolean(), nullable=False),
        sa.Column("processing_ms", sa.Float(), nullable=False),
        sa.Column("input_audio_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_turn_metrics_call_id"),
        "turn_metrics",
        ["call_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_turn_metrics_channel"),
        "turn_metrics",
        ["channel"],
        unique=False,
    )
    op.create_index(
        op.f("ix_turn_metrics_tenant_id"),
        "turn_metrics",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_turn_metrics_tenant_id"),
        table_name="turn_metrics",
    )
    op.drop_index(
        op.f("ix_turn_metrics_channel"),
        table_name="turn_metrics",
    )
    op.drop_index(
        op.f("ix_turn_metrics_call_id"),
        table_name="turn_metrics",
    )
    op.drop_table("turn_metrics")
