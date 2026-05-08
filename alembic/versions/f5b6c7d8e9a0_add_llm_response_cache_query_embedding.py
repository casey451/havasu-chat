"""add query_embedding column to llm_response_cache (cache v2)

§4.3 (cache v2 / similarity matching): introduces a JSON-encoded query
embedding column on ``llm_response_cache`` so the lookup path can fall back
to a cosine-similarity scan when the exact-match key misses. Nullable —
pre-v2 rows (and rows whose embedding API call failed at store() time)
serve exact-match hits and are simply skipped during the similarity scan.

Cross-dialect (SQLite + Postgres). No index — sequential scan is fine while
the cache is small (handful of MB even at full saturation), and a B-tree
index on a JSON blob wouldn't accelerate cosine similarity anyway.

Revision ID: f5b6c7d8e9a0
Revises: c1a2b3c4d5e6
Create Date: 2026-05-08

NB: this migration chains off ``c1a2b3c4d5e6`` (the latest committed head at
the time of writing). The home-page-design branch carries two parallel
migrations chaining off the same point (``d2e3f4a5b6c7`` /
``e3f4a5b6c7d8``); when those land they'll need a one-line merge revision
to reconcile the alembic graph. Standard fan-in pattern, not a real
conflict.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f5b6c7d8e9a0"
down_revision: Union[str, Sequence[str], None] = "c1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llm_response_cache",
        sa.Column("query_embedding", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llm_response_cache", "query_embedding")
