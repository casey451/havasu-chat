"""Phase A4: upgrade_requests table (merchant featured-listing requests).

Adds the ``upgrade_requests`` table backing the claim-your-listing upgrade
funnel. A verified merchant requests that their listing be featured in a
sponsor slot; an admin reviews and, on approval, may spin out a live Sponsor
row. NO billing/payment columns — pricing is a Casey product decision.

Purely additive (one new table); reversible.

Revision ID: a4b1c2d3e4f5
Revises: d1e2f3a4b5c6
Create Date: 2026-06-02
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a4b1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "upgrade_requests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=True),
        sa.Column(
            "requested_slot", sa.String(length=32), nullable=False, server_default="spotlight"
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("created_sponsor_id", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'declined')",
            name="ck_upgrade_requests_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_upgrade_requests_status", "upgrade_requests", ["status"])
    op.create_index("ix_upgrade_requests_entity_id", "upgrade_requests", ["entity_id"])
    op.create_index("ix_upgrade_requests_user_id", "upgrade_requests", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_upgrade_requests_user_id", table_name="upgrade_requests")
    op.drop_index("ix_upgrade_requests_entity_id", table_name="upgrade_requests")
    op.drop_index("ix_upgrade_requests_status", table_name="upgrade_requests")
    op.drop_table("upgrade_requests")
