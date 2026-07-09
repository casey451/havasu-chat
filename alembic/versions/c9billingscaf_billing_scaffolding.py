"""C9/F4: billing scaffolding — placements Stripe columns + revenue_events ledger

Revision ID: c9billingscaf
Revises: b7islocalcol
Create Date: 2026-06-15

Additive only. Three NEW nullable columns on ``placements`` (Stripe linkage,
all NULL today) and one NEW ``revenue_events`` ledger table. Nothing writes to
either until billing is enabled (STRIPE_BILLING_ENABLED + keys + the ``stripe``
package), so this is dormant on deploy.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9billingscaf"
down_revision: Union[str, Sequence[str], None] = "b7islocalcol"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "placements", sa.Column("stripe_customer_id", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "placements", sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "placements",
        sa.Column("stripe_checkout_session_id", sa.String(length=255), nullable=True),
    )

    op.create_table(
        "revenue_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("provider_id", sa.String(), nullable=True),
        sa.Column("placement_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="usd"),
        sa.Column("stripe_event_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_object_id", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('payment', 'renewal', 'refund', 'lapse', 'subscription_canceled')",
            name="ck_revenue_events_kind",
        ),
        sa.UniqueConstraint("stripe_event_id", name="uq_revenue_events_stripe_event_id"),
    )
    op.create_index("ix_revenue_events_provider_id", "revenue_events", ["provider_id"])
    op.create_index("ix_revenue_events_placement_id", "revenue_events", ["placement_id"])
    op.create_index("ix_revenue_events_created_at", "revenue_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_revenue_events_created_at", table_name="revenue_events")
    op.drop_index("ix_revenue_events_placement_id", table_name="revenue_events")
    op.drop_index("ix_revenue_events_provider_id", table_name="revenue_events")
    op.drop_table("revenue_events")
    op.drop_column("placements", "stripe_checkout_session_id")
    op.drop_column("placements", "stripe_subscription_id")
    op.drop_column("placements", "stripe_customer_id")
