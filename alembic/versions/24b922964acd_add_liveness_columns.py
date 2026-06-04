"""Liveness ranking — newest_review_at + liveness_score columns.

Adds the staleness signal (``providers.newest_review_at``) and the computed
0–1 liveness blend (``providers.liveness_score``, indexed) plus a forward-compat
mirror on the unified entity (``entities.liveness_score``). Purely structural and
nullable — the data fill is a separate idempotent step
(``scripts/backfill_liveness.py``) so this migration re-runs cleanly on any
environment. See LIVENESS_RANKING_HANDOFF_2026-06-03.md.

Revision ID: 24b922964acd
Revises: e2f3a4b5c6d7
Create Date: 2026-06-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "24b922964acd"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "providers",
        sa.Column("newest_review_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("providers", sa.Column("liveness_score", sa.Float(), nullable=True))
    op.create_index("ix_providers_liveness_score", "providers", ["liveness_score"])
    op.add_column("entities", sa.Column("liveness_score", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("entities", "liveness_score")
    op.drop_index("ix_providers_liveness_score", table_name="providers")
    op.drop_column("providers", "liveness_score")
    op.drop_column("providers", "newest_review_at")
