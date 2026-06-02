"""Phase 2 Slice 1: query_log telemetry columns (min_layer, sub_intent).

Adds two additive nullable columns to ``query_log`` so the intent layer can
record which matcher layer resolved a turn (``min_layer``: L1..L4 / a future
"clarify" marker, hence String(8)) and the legacy sub-intent on fall-through
turns. Nullable with no server_default -> no backfill lock on Postgres; the
SQLite test DB is unaffected. Purely structural; reversible.

Revision ID: d1e2f3a4b5c6
Revises: v1c3d4e5f6a8
Create Date: 2026-06-01
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "v1c3d4e5f6a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("query_log", sa.Column("min_layer", sa.String(length=8), nullable=True))
    op.add_column("query_log", sa.Column("sub_intent", sa.String(length=64), nullable=True))
    op.create_index("ix_query_log_min_layer", "query_log", ["min_layer"])


def downgrade() -> None:
    op.drop_index("ix_query_log_min_layer", table_name="query_log")
    op.drop_column("query_log", "sub_intent")
    op.drop_column("query_log", "min_layer")
