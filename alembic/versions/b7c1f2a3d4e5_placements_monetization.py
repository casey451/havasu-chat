"""Phase F1: placements + placement_prices (monetization data model)

Revision ID: b7c1f2a3d4e5
Revises: 304cc3843188
Create Date: 2026-06-14

Additive only — two NEW tables, no changes to any existing table. The legacy
sponsor tables are untouched.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7c1f2a3d4e5"
down_revision: Union[str, Sequence[str], None] = "304cc3843188"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TYPES = "('homepage_rotating', 'category_rank', 'page_ad')"
_STATUSES = "('pending', 'active', 'expired', 'released')"
_BILLING = "('monthly', 'recurring')"


def upgrade() -> None:
    op.create_table(
        "placements",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "provider_id", sa.String(),
            sa.ForeignKey("providers.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("placement_type", sa.String(length=24), nullable=False),
        sa.Column("category_slug", sa.String(length=64), nullable=True),
        sa.Column("rank_tier", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("billing_type", sa.String(length=16), nullable=False, server_default="monthly"),
        sa.Column("price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("paid_through", sa.DateTime(), nullable=True),
        sa.Column("creative_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(f"placement_type IN {_TYPES}", name="ck_placements_type"),
        sa.CheckConstraint(f"status IN {_STATUSES}", name="ck_placements_status"),
        sa.CheckConstraint(f"billing_type IN {_BILLING}", name="ck_placements_billing_type"),
        sa.CheckConstraint("rank_tier IS NULL OR (rank_tier BETWEEN 1 AND 5)",
                           name="ck_placements_rank_tier"),
    )
    op.create_index("ix_placements_type_category", "placements",
                    ["placement_type", "category_slug"])
    op.create_index("ix_placements_status", "placements", ["status"])
    op.create_index("ix_placements_provider_id", "placements", ["provider_id"])

    op.create_table(
        "placement_prices",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("placement_type", sa.String(length=24), nullable=False),
        sa.Column("category_slug", sa.String(length=64), nullable=True),
        sa.Column("rank_tier", sa.Integer(), nullable=True),
        sa.Column("price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(f"placement_type IN {_TYPES}", name="ck_placement_prices_type"),
        sa.CheckConstraint("rank_tier IS NULL OR (rank_tier BETWEEN 1 AND 5)",
                           name="ck_placement_prices_rank_tier"),
        sa.UniqueConstraint("placement_type", "category_slug", "rank_tier",
                            name="uq_placement_prices_key"),
    )


def downgrade() -> None:
    op.drop_table("placement_prices")
    op.drop_index("ix_placements_provider_id", table_name="placements")
    op.drop_index("ix_placements_status", table_name="placements")
    op.drop_index("ix_placements_type_category", table_name="placements")
    op.drop_table("placements")
