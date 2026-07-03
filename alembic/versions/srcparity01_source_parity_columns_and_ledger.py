"""Source-parity campaign: region/category_provenance/category columns + ledger.

Additive schema for docs/audits/2026-07/PARITY_AND_COMPLETENESS_PLAN_2026-07-03.md:
  * providers.region, providers.category_provenance
  * events.category, events.region
  * source_listings + source_events coverage-ledger tables

All nullable / additive; no serving path reads the new columns yet. No backfill
here (that's the dry-run-gated data ops in later PRs).

Revision ID: srcparity01
Revises: linkassess02
Create Date: 2026-07-03
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "srcparity01"
down_revision: Union[str, Sequence[str], None] = "linkassess02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- new columns on existing tables ---
    op.add_column("providers", sa.Column("region", sa.String(length=32), nullable=True))
    op.add_column(
        "providers", sa.Column("category_provenance", sa.String(length=32), nullable=True)
    )
    op.create_index("ix_providers_region", "providers", ["region"], unique=False)

    op.add_column("events", sa.Column("category", sa.String(length=48), nullable=True))
    op.add_column("events", sa.Column("region", sa.String(length=32), nullable=True))
    op.create_index("ix_events_category", "events", ["category"], unique=False)
    op.create_index("ix_events_region", "events", ["region"], unique=False)

    # --- coverage ledger: business listings ---
    op.create_table(
        "source_listings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=48), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("source_category", sa.String(length=128), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("region", sa.String(length=32), nullable=True),
        sa.Column("mapped_leaf", sa.String(length=64), nullable=True),
        sa.Column(
            "match_status",
            sa.String(length=24),
            nullable=False,
            server_default="missing",
        ),
        sa.Column("matched_provider_id", sa.String(), nullable=True),
        sa.Column("exclusion_reason", sa.String(length=64), nullable=True),
        sa.Column("first_seen", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["matched_provider_id"], ["providers.id"]),
        sa.UniqueConstraint("source", "source_url", name="uq_source_listings_source_url"),
        sa.CheckConstraint(
            "match_status IN ('matched', 'missing', 'miscategorized', 'excluded')",
            name="ck_source_listings_match_status",
        ),
    )
    op.create_index("ix_source_listings_source", "source_listings", ["source"], unique=False)
    op.create_index("ix_source_listings_region", "source_listings", ["region"], unique=False)
    op.create_index(
        "ix_source_listings_match_status", "source_listings", ["match_status"], unique=False
    )

    # --- coverage ledger: events ---
    op.create_table(
        "source_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=48), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("source_category", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("venue", sa.String(), nullable=True),
        sa.Column("region", sa.String(length=32), nullable=True),
        sa.Column("mapped_category", sa.String(length=48), nullable=True),
        sa.Column(
            "match_status",
            sa.String(length=24),
            nullable=False,
            server_default="missing",
        ),
        sa.Column("matched_event_id", sa.String(), nullable=True),
        sa.Column("exclusion_reason", sa.String(length=64), nullable=True),
        sa.Column("first_seen", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["matched_event_id"], ["events.id"]),
        sa.UniqueConstraint("source", "source_url", name="uq_source_events_source_url"),
        sa.CheckConstraint(
            "match_status IN ('matched', 'missing', 'miscategorized', 'excluded')",
            name="ck_source_events_match_status",
        ),
    )
    op.create_index("ix_source_events_source", "source_events", ["source"], unique=False)
    op.create_index("ix_source_events_region", "source_events", ["region"], unique=False)
    op.create_index(
        "ix_source_events_match_status", "source_events", ["match_status"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_source_events_match_status", table_name="source_events")
    op.drop_index("ix_source_events_region", table_name="source_events")
    op.drop_index("ix_source_events_source", table_name="source_events")
    op.drop_table("source_events")

    op.drop_index("ix_source_listings_match_status", table_name="source_listings")
    op.drop_index("ix_source_listings_region", table_name="source_listings")
    op.drop_index("ix_source_listings_source", table_name="source_listings")
    op.drop_table("source_listings")

    op.drop_index("ix_events_region", table_name="events")
    op.drop_index("ix_events_category", table_name="events")
    op.drop_column("events", "region")
    op.drop_column("events", "category")

    op.drop_index("ix_providers_region", table_name="providers")
    op.drop_column("providers", "category_provenance")
    op.drop_column("providers", "region")
