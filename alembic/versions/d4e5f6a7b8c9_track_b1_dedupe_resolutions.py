"""Track B1 dedupe: resolutions table + provider resolution-path columns.

Adds the persistence layer for the dedupe review queue
(app/admin/provider_merge_review.py):

  * ``dedupe_resolutions`` — one row per reviewed candidate pair so the
    live-computed queue stops resurfacing pairs a human already resolved
    (not_duplicate / multi_location / parent_child / merged).
  * ``providers.location_group_id`` — same-business-multiple-locations link
    key (rows sharing it are distinct listings of one business; never merged).
  * ``providers.parent_provider_id`` — parent-org/department shape (the
    Specialty Associates pattern); self-referential FK.

All additive: new table + two nullable columns. No data is touched, so
downgrade is a clean drop. See HAVA_AUDIT_AND_TAXONOMY_REBUILD.md (Track B1)
and docs/PROMPT_CLAUDE_CODE_TRACK_B_2026-06-10.md.

Revision ID: d4e5f6a7b8c9
Revises: e9b5d7f3a1c6
Create Date: 2026-06-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "e9b5d7f3a1c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dedupe_resolutions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("pair_key", sa.String(length=80), nullable=False),
        sa.Column("provider_id_a", sa.String(), nullable=False),
        sa.Column("provider_id_b", sa.String(), nullable=False),
        sa.Column("resolution", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.String(length=120), nullable=False, server_default="admin"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("pair_key", name="uq_dedupe_resolutions_pair_key"),
        sa.CheckConstraint(
            "resolution IN ('not_duplicate', 'multi_location', 'parent_child', 'merged')",
            name="ck_dedupe_resolutions_resolution",
        ),
    )
    op.create_index(
        "ix_dedupe_resolutions_provider_id_a", "dedupe_resolutions", ["provider_id_a"]
    )
    op.create_index(
        "ix_dedupe_resolutions_provider_id_b", "dedupe_resolutions", ["provider_id_b"]
    )

    op.add_column(
        "providers", sa.Column("location_group_id", sa.String(length=36), nullable=True)
    )
    op.create_index("ix_providers_location_group_id", "providers", ["location_group_id"])
    op.add_column(
        "providers", sa.Column("parent_provider_id", sa.String(), nullable=True)
    )
    op.create_index("ix_providers_parent_provider_id", "providers", ["parent_provider_id"])
    # The self-referential FK constraint is Postgres-only: SQLite (the test
    # DB) cannot ALTER-add a constraint outside batch mode, and a full
    # providers-table rebuild for a soft-integrity column isn't worth the
    # reflection risk. SQLite's create_all path still gets the FK inline from
    # the model; its migration path runs with foreign_keys OFF anyway.
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_providers_parent_provider_id",
            "providers",
            "providers",
            ["parent_provider_id"],
            ["id"],
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint(
            "fk_providers_parent_provider_id", "providers", type_="foreignkey"
        )
    op.drop_index("ix_providers_parent_provider_id", table_name="providers")
    op.drop_column("providers", "parent_provider_id")
    op.drop_index("ix_providers_location_group_id", table_name="providers")
    op.drop_column("providers", "location_group_id")
    op.drop_index("ix_dedupe_resolutions_provider_id_b", table_name="dedupe_resolutions")
    op.drop_index("ix_dedupe_resolutions_provider_id_a", table_name="dedupe_resolutions")
    op.drop_table("dedupe_resolutions")
