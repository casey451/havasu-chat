"""Taxonomy tree — categories.parent_id + level (A.3 step 1).

Adds a self-referential parent + a 0/1 ``level`` discriminator to ``categories``
so the flat table can hold departments (level 0, ``parent_id`` NULL) and leaves
(level 1, ``parent_id`` = dept id). Purely structural and nullable/defaulted —
the data fill (15 departments + 126 leaves) is a separate idempotent step
(``scripts/seed_taxonomy.py``), and the entity remap is gated/dry-run
(``scripts/apply_taxonomy_remap.py``). See docs/proposals/A3-apply-spec.md.

Revision ID: b2d4f6a8c0e2
Revises: a7c9e1f3b5d7
Create Date: 2026-06-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2d4f6a8c0e2"
down_revision: str | Sequence[str] | None = "a7c9e1f3b5d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite cannot ALTER-ADD a column that carries a FOREIGN KEY constraint
    # ("No support for ALTER of constraints"), and its test/dev engine runs with
    # foreign_keys OFF anyway — so add a plain integer there and keep the real
    # self-referential FK on Postgres (prod). Tree integrity is enforced at the
    # application layer (scripts/seed_taxonomy.py) regardless of dialect.
    is_sqlite = op.get_bind().dialect.name == "sqlite"
    parent_col = (
        sa.Column("parent_id", sa.Integer(), nullable=True)
        if is_sqlite
        else sa.Column(
            "parent_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=True
        )
    )
    op.add_column("categories", parent_col)
    op.add_column(
        "categories",
        sa.Column("level", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    op.create_index("ix_categories_parent", "categories", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_categories_parent", table_name="categories")
    op.drop_column("categories", "level")
    op.drop_column("categories", "parent_id")
