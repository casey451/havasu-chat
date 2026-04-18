"""add source to events; add verified to events and programs

Revision ID: d4b7e2f1c902
Revises: c3a9e2f5b801
Create Date: 2026-04-17

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4b7e2f1c902"
down_revision: Union[str, Sequence[str], None] = "c3a9e2f5b801"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # events.source — new column, defaults to 'admin' for existing rows.
    op.add_column(
        "events",
        sa.Column("source", sa.String(), nullable=False, server_default="admin"),
    )
    # events.verified — new column, defaults to FALSE.
    op.add_column(
        "events",
        sa.Column(
            "verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # programs.verified — new column on the Z-1 programs table.
    op.add_column(
        "programs",
        sa.Column(
            "verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Backfill existing admin-sourced rows as verified (pre-dates the two-tier model).
    op.execute("UPDATE events SET verified = TRUE WHERE source = 'admin'")
    op.execute("UPDATE programs SET verified = TRUE WHERE source = 'admin'")


def downgrade() -> None:
    op.drop_column("programs", "verified")
    op.drop_column("events", "verified")
    op.drop_column("events", "source")
