"""Phase 9a — events RRULE columns, lifecycle CHECK, indexes.

Revision ID: a9b0c1d2e3f4
Revises: d8e9f0a1b2c3
Create Date: 2026-05-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9b0c1d2e3f4"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("rrule", sa.String(length=255), nullable=True))
    op.add_column("events", sa.Column("rdate", sa.JSON(), nullable=True))
    op.add_column("events", sa.Column("exdate", sa.JSON(), nullable=True))
    op.add_column("events", sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("events", sa.Column("cancellation_reason", sa.Text(), nullable=True))
    op.add_column(
        "events",
        sa.Column(
            "operator_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("events", sa.Column("capacity", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("capacity_source", sa.String(length=64), nullable=True))

    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_events_status",
            "status IN ("
            "'draft', 'live', 'cancelled', 'expired', "
            "'pending_review', 'deleted'"
            ")",
        )

    op.create_index("ix_events_status_date", "events", ["status", "date"], unique=False)
    op.create_index(
        "ix_events_is_recurring_date",
        "events",
        ["is_recurring", "date"],
        unique=False,
    )
    op.create_index(
        "ix_events_provider_id_date",
        "events",
        ["provider_id", "date"],
        unique=False,
    )
    op.create_index("ix_events_scraped_at", "events", ["scraped_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_events_scraped_at", table_name="events")
    op.drop_index("ix_events_provider_id_date", table_name="events")
    op.drop_index("ix_events_is_recurring_date", table_name="events")
    op.drop_index("ix_events_status_date", table_name="events")

    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.drop_constraint("ck_events_status", type_="check")

    op.drop_column("events", "capacity_source")
    op.drop_column("events", "capacity")
    op.drop_column("events", "operator_override")
    op.drop_column("events", "cancellation_reason")
    op.drop_column("events", "scraped_at")
    op.drop_column("events", "exdate")
    op.drop_column("events", "rdate")
    op.drop_column("events", "rrule")
