"""appointment_timezone_snapshot

Revision ID: 6b57a636712c
Revises: 53701ff484ff
Create Date: 2026-10-04 22:40:54.079389
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6b57a636712c"
down_revision: str | Sequence[str] | None = "53701ff484ff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column(
            "starts_at_iso",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.add_column(
        "appointments",
        sa.Column(
            "ends_at_iso",
            sa.String(length=64),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("appointments", "ends_at_iso")
    op.drop_column("appointments", "starts_at_iso")
