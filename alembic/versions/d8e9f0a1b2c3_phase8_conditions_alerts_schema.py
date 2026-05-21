"""Phase 8a — external_conditions_cache circuit-breaker columns + alert dedup statuses.

Revision ID: d8e9f0a1b2c3
Revises: c9d0e1f2a3b4
Create Date: 2026-05-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "external_conditions_cache",
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "external_conditions_cache",
        sa.Column("next_attempt_after", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_external_conditions_cache_next_attempt_after",
        "external_conditions_cache",
        ["next_attempt_after"],
        unique=False,
    )

    with op.batch_alter_table("alerts_dispatched", schema=None) as batch_op:
        batch_op.drop_constraint(
            "ck_alerts_dispatched_delivery_status", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_alerts_dispatched_delivery_status",
            "delivery_status IN ("
            "'queued', 'sent', 'failed', 'bounced', "
            "'suppressed_dedupe', 'suppressed_paused'"
            ")",
        )


def downgrade() -> None:
    with op.batch_alter_table("alerts_dispatched", schema=None) as batch_op:
        batch_op.drop_constraint(
            "ck_alerts_dispatched_delivery_status", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_alerts_dispatched_delivery_status",
            "delivery_status IN ('queued', 'sent', 'failed', 'bounced')",
        )

    op.drop_index(
        "ix_external_conditions_cache_next_attempt_after",
        table_name="external_conditions_cache",
    )
    op.drop_column("external_conditions_cache", "next_attempt_after")
    op.drop_column("external_conditions_cache", "last_attempt_at")
