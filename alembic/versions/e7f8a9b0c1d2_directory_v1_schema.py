"""add directory pivot V1 schema (Category + category_id FKs + attributes/district on Provider)

Strategic pivot 2026-05-12: havasu-chat becoming structured directory.
This migration adds the `categories` lookup table, FK references from
providers/programs, and the operator-curated `attributes` JSON +
`district` string columns on providers. The 12 categories are seeded
as part of upgrade. Coexists with the legacy free-text
`providers.category` and `programs.activity_category` columns
(additive, no removals).

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-05-13

"""

from datetime import UTC, datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CATEGORIES = [
    {"slug": "eat-and-drink", "name": "Eat & Drink", "sort_order": 10},
    {"slug": "events", "name": "Events", "sort_order": 20},
    {"slug": "family", "name": "Family", "sort_order": 30},
    {"slug": "home-services", "name": "Home Services", "sort_order": 40},
    {"slug": "health", "name": "Health", "sort_order": 50},
    {"slug": "on-the-water", "name": "On the Water", "sort_order": 60},
    {"slug": "outdoors-and-parks", "name": "Outdoors & Parks", "sort_order": 70},
    {"slug": "shopping", "name": "Shopping", "sort_order": 80},
    {"slug": "auto-and-gas", "name": "Auto & Gas", "sort_order": 90},
    {"slug": "lodging", "name": "Lodging", "sort_order": 100},
    {"slug": "pets", "name": "Pets", "sort_order": 110},
    {"slug": "community", "name": "Community", "sort_order": 120},
]


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_categories_slug", "categories", ["slug"], unique=True)

    categories_tbl = sa.table(
        "categories",
        sa.column("slug", sa.String(64)),
        sa.column("name", sa.String(128)),
        sa.column("sort_order", sa.Integer()),
        sa.column("created_at", sa.DateTime()),
    )
    op.bulk_insert(
        categories_tbl,
        [{**row, "created_at": datetime.now(UTC)} for row in _CATEGORIES],
    )

    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("category_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("attributes", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("district", sa.String(64), nullable=True))
        batch_op.create_foreign_key(
            "fk_providers_category_id",
            "categories",
            ["category_id"],
            ["id"],
        )
    op.create_index("ix_providers_category_id", "providers", ["category_id"])

    with op.batch_alter_table("programs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("category_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_programs_category_id",
            "categories",
            ["category_id"],
            ["id"],
        )
    op.create_index("ix_programs_category_id", "programs", ["category_id"])


def downgrade() -> None:
    op.drop_index("ix_programs_category_id", table_name="programs")
    with op.batch_alter_table("programs", schema=None) as batch_op:
        batch_op.drop_constraint("fk_programs_category_id", type_="foreignkey")
        batch_op.drop_column("category_id")

    op.drop_index("ix_providers_category_id", table_name="providers")
    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.drop_constraint("fk_providers_category_id", type_="foreignkey")
        batch_op.drop_column("district")
        batch_op.drop_column("attributes")
        batch_op.drop_column("category_id")

    op.drop_index("ix_categories_slug", table_name="categories")
    op.drop_table("categories")
