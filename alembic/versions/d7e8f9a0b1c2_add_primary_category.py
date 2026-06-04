"""WP-9 taxonomy — providers.primary_category (+ entities forward-compat mirror).

Adds the single canonical category slug (one of Home's 12) as a nullable, indexed
column on ``providers`` and a forward-compat mirror on ``entities`` (matching the
liveness pattern). Purely structural and nullable — the data fill is a separate
idempotent step (``scripts/backfill_primary_category.py``) so this migration
re-runs cleanly on any environment. See WP-9 brief / audit R2.

Revision ID: d7e8f9a0b1c2
Revises: b9c0d1e2f3a4
Create Date: 2026-06-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, Sequence[str], None] = "b9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("providers", sa.Column("primary_category", sa.String(), nullable=True))
    op.create_index(
        "ix_providers_primary_category", "providers", ["primary_category"]
    )
    op.add_column("entities", sa.Column("primary_category", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("entities", "primary_category")
    op.drop_index("ix_providers_primary_category", table_name="providers")
    op.drop_column("providers", "primary_category")
