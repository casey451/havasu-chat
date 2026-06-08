"""Manual-invoice ad reservations — additive ``ad_reservations`` table.

Backs the /portal/advertise "Reserve this spot" flow: a prospect reserves an
ad placement, a server-side reservation lands here, and the operator is
notified. NO payment/billing columns — Casey closes the deal by invoice
offline. Purely additive (one new table); reversible.

Revision ID: f1a7c9e2b3d4
Revises: a7c9e1f3b5d7
Create Date: 2026-06-08

``created_at`` uses a ``sa.func.now()`` server default (scrape_captures /
photos-table precedent). ``status`` / ``source`` carry string server defaults
to match the model.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f1a7c9e2b3d4"
down_revision: Union[str, Sequence[str], None] = "a7c9e1f3b5d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ad_reservations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("product_key", sa.String(length=64), nullable=False),
        sa.Column("product_name", sa.String(), nullable=False),
        sa.Column("business_name", sa.String(), nullable=False),
        sa.Column("contact_name", sa.String(), nullable=False),
        sa.Column("contact_email", sa.String(), nullable=False),
        sa.Column("contact_phone", sa.String(), nullable=True),
        sa.Column("category_or_notes", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "source",
            sa.String(length=64),
            nullable=False,
            server_default="advertise_page",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'contacted', 'closed', 'declined')",
            name="ck_ad_reservations_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ad_reservations_status", "ad_reservations", ["status"], unique=False
    )
    op.create_index(
        "ix_ad_reservations_created_at", "ad_reservations", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_ad_reservations_created_at", table_name="ad_reservations")
    op.drop_index("ix_ad_reservations_status", table_name="ad_reservations")
    op.drop_table("ad_reservations")
