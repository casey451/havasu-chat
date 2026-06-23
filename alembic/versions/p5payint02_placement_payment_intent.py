"""add placements.stripe_payment_intent_id

Refund support (P5): an admin-initiated refund calls
``stripe.Refund.create(payment_intent=...)``, so the placement must carry the
latest charge's PaymentIntent. The webhook captures it on
``checkout.session.completed`` / ``invoice.paid``. Additive + nullable: existing
rows stay NULL (no charge captured pre-billing) and nothing else changes.

Revision ID: p5payint02
Revises: p5feedback01
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p5payint02"
down_revision = "p5feedback01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "placements",
        sa.Column("stripe_payment_intent_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("placements", "stripe_payment_intent_id")
