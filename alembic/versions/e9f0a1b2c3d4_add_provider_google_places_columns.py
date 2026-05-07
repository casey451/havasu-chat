"""add provider Google Places columns for LHC business pull

Phase 1 of the Lake Havasu City Google Places pull (see
relay/HAVA_BUSINESSES_EXECUTION_PLAN_2026-05-06.md). This migration is
drafted in Phase 1 but executed in Phase 5, immediately before the
filter+load step.

Additive only. Extends the existing `providers` table per §8 of
relay/HAVA_GOOGLE_BUSINESSES_HANDOFF_2026-05-06.md so that businesses
sourced from Google Places live alongside event/program providers in the
same entity. Provenance is signalled by `google_place_id IS NOT NULL`.

What this does on upgrade:
  1. Pre-flight: abort if existing rows have duplicate non-null
     `google_place_id` values — the partial unique index below would
     fail otherwise, and we want a clean error rather than half-applied
     DDL.
  2. Drop the plain index `ix_providers_google_place_id` (added in
     b8c9d0e1f2a3) and replace it with a partial unique index that
     enforces uniqueness only when `google_place_id` is not null. Plain
     event/program providers (with NULL Place IDs) keep coexisting in
     the same table without collision.
  3. Add the eight Google-sourced columns + `last_google_scraped_at`.
  4. Add `zip` (String) with a plain index — Phase 5 filters by ZIP
     and downstream chat retrieval will likely filter by it too.

Notes:
  - JSON columns use `sa.JSON()` to match the existing pattern across
    `raw_enrichment_json`, `embedding`, `hours_structured`, etc.
    SQLAlchemy dispatches to JSON on SQLite and JSON on Postgres; this
    keeps the schema consistent rather than mixing JSONB on a single
    column.
  - `google_hours` is kept separate from the existing `hours_structured`
    column. `hours_structured` is source-agnostic; `google_hours`
    preserves the raw Google `regularOpeningHours` shape so future
    refresh / provenance work has fidelity.
  - `batch_alter_table` is used for index work to keep the DDL
    cross-dialect (SQLite + Postgres).

Revision ID: e9f0a1b2c3d4
Revises: a7b8c9d0e1f2
Create Date: 2026-05-06

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Pre-flight: existing rows must not have duplicate non-null
    # google_place_id values, or the partial unique index below will
    # fail mid-DDL. The plain index added in b8c9d0e1f2a3 did not enforce
    # uniqueness, so duplicates are theoretically possible.
    bind = op.get_bind()
    dup_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM ("
            "  SELECT google_place_id FROM providers "
            "  WHERE google_place_id IS NOT NULL "
            "  GROUP BY google_place_id "
            "  HAVING COUNT(*) > 1"
            ") AS d"
        )
    ).scalar()
    if dup_count and dup_count > 0:
        raise RuntimeError(
            f"Migration aborted: {dup_count} duplicate non-null "
            "google_place_id value(s) in providers. Resolve duplicates "
            "before applying the partial unique index. "
            "See relay/HAVA_BUSINESSES_EXECUTION_PLAN_2026-05-06.md §3."
        )

    # Replace the plain index with a partial unique index.
    op.drop_index("ix_providers_google_place_id", table_name="providers")
    op.create_index(
        "ux_providers_google_place_id",
        "providers",
        ["google_place_id"],
        unique=True,
        postgresql_where=sa.text("google_place_id IS NOT NULL"),
        sqlite_where=sa.text("google_place_id IS NOT NULL"),
    )

    # Google Places enrichment columns.
    op.add_column(
        "providers", sa.Column("google_primary_category", sa.String(), nullable=True)
    )
    op.add_column(
        "providers", sa.Column("google_categories", sa.JSON(), nullable=True)
    )
    op.add_column("providers", sa.Column("google_rating", sa.Float(), nullable=True))
    op.add_column(
        "providers", sa.Column("google_review_count", sa.Integer(), nullable=True)
    )
    op.add_column(
        "providers", sa.Column("google_review_snippets", sa.JSON(), nullable=True)
    )
    op.add_column(
        "providers", sa.Column("google_photo_refs", sa.JSON(), nullable=True)
    )
    op.add_column("providers", sa.Column("google_hours", sa.JSON(), nullable=True))
    op.add_column(
        "providers",
        sa.Column("last_google_scraped_at", sa.DateTime(), nullable=True),
    )

    # ZIP — needed for Phase 5 post-filtering and downstream retrieval.
    op.add_column("providers", sa.Column("zip", sa.String(), nullable=True))
    op.create_index("ix_providers_zip", "providers", ["zip"])


def downgrade() -> None:
    op.drop_index("ix_providers_zip", table_name="providers")
    op.drop_column("providers", "zip")

    op.drop_column("providers", "last_google_scraped_at")
    op.drop_column("providers", "google_hours")
    op.drop_column("providers", "google_photo_refs")
    op.drop_column("providers", "google_review_snippets")
    op.drop_column("providers", "google_review_count")
    op.drop_column("providers", "google_rating")
    op.drop_column("providers", "google_categories")
    op.drop_column("providers", "google_primary_category")

    # Restore the plain index on google_place_id.
    op.drop_index("ux_providers_google_place_id", table_name="providers")
    op.create_index(
        "ix_providers_google_place_id", "providers", ["google_place_id"]
    )
