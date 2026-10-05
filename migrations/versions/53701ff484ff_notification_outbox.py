"""notification_outbox

Revision ID: 53701ff484ff
Revises: 9cdcbc741f53
Create Date: 2026-10-04 22:29:43.644813
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "53701ff484ff"
down_revision: str | Sequence[str] | None = "9cdcbc741f53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("appointment_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("recipient", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "provider_message_id",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"],
            ["appointments.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "appointment_id",
            "kind",
            name="uq_notification_tenant_appointment_kind",
        ),
    )
    op.create_index(
        op.f("ix_notification_outbox_appointment_id"),
        "notification_outbox",
        ["appointment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_outbox_kind"),
        "notification_outbox",
        ["kind"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_outbox_next_attempt_at"),
        "notification_outbox",
        ["next_attempt_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_outbox_tenant_id"),
        "notification_outbox",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_notification_outbox_tenant_id"),
        table_name="notification_outbox",
    )
    op.drop_index(
        op.f("ix_notification_outbox_next_attempt_at"),
        table_name="notification_outbox",
    )
    op.drop_index(
        op.f("ix_notification_outbox_kind"),
        table_name="notification_outbox",
    )
    op.drop_index(
        op.f("ix_notification_outbox_appointment_id"),
        table_name="notification_outbox",
    )
    op.drop_table("notification_outbox")
