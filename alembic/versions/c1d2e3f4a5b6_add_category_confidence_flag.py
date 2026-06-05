"""Category patrol — category_confidence + category_flagged_at columns.

Additive, nullable, and never read by any serving path (mirrors the
liveness_score pattern in 24b922964acd). ``category_confidence`` is the patrol's
0-1 confidence that a provider's ``primary_category`` is *wrong*;
``category_flagged_at`` is set when the patrol queues the row for the admin
"miscategorized?" review list and cleared when an admin resolves it. The data
fill is a separate, dry-run-gated step (``scripts/category_patrol.py``), so this
migration re-runs cleanly on any environment.

Revision ID: c1d2e3f4a5b6
Revises: f6a7b8c9d0e2
Create Date: 2026-06-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("providers", sa.Column("category_confidence", sa.Float(), nullable=True))
    op.add_column(
        "providers",
        sa.Column("category_flagged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_providers_category_flagged_at", "providers", ["category_flagged_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_providers_category_flagged_at", table_name="providers")
    op.drop_column("providers", "category_flagged_at")
    op.drop_column("providers", "category_confidence")
