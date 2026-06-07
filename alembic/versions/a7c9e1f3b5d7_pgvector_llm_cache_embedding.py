"""pgvector column + HNSW index for llm_response_cache similarity (HANDOFF #2)

Postgres-only: adds a native ``vector(1536)`` column (``embedding``) to
``llm_response_cache``, backfills it from the JSON ``query_embedding`` column
for rows whose stored vector is exactly 1536-dim (other dims are skipped),
and creates an HNSW cosine index. The JSON column is intentionally KEPT
during the transition — the Python-scan fallback (SQLite tests, any
non-pgvector Postgres) still reads it, and dropping it is a later cleanup.

On SQLite (test setup) and any non-Postgres dialect this migration is a
no-op in both directions — the runtime code falls back to the existing
Python cosine scan there.

Index choice: HNSW over IVFFlat. The cache is small (7-day TTL; hundreds of
rows), so either is instant — HNSW is chosen because it needs no training
step and behaves well as the table grows; rebuild cost is irrelevant at this
size. Tradeoff documented per CLAUDE_CODE_HANDOFF.md #2.

``CREATE EXTENSION vector`` requires the extension to be AVAILABLE on the
server (pgvector ships on Railway's Postgres images and on the VPS staging
``pgvector/pgvector:pg16`` container). Per the handoff gate, Casey must
confirm availability on Railway BEFORE this merges; rehearse with
``scripts/rehearse_migration.sh --check-downgrade`` first.

Revision ID: a7c9e1f3b5d7
Revises: e5f6a7b8c9d0
Create Date: 2026-06-06
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a7c9e1f3b5d7"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DIM = 1536


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        f"ALTER TABLE llm_response_cache ADD COLUMN IF NOT EXISTS embedding vector({_DIM})"
    )
    # Backfill: per-row in Python (not a bulk ::vector cast) so a single
    # malformed JSON blob can't abort the whole migration. Cache table is
    # small (7-day TTL), so row-at-a-time is fine.
    rows = bind.execute(
        sa.text(
            "SELECT id, query_embedding FROM llm_response_cache "
            "WHERE query_embedding IS NOT NULL AND embedding IS NULL"
        )
    ).fetchall()
    for row_id, blob in rows:
        try:
            vec = json.loads(blob)
        except (TypeError, ValueError):
            continue
        if not isinstance(vec, list) or len(vec) != _DIM:
            continue
        try:
            literal = "[" + ",".join(repr(float(x)) for x in vec) + "]"
        except (TypeError, ValueError):
            continue
        bind.execute(
            sa.text(
                "UPDATE llm_response_cache SET embedding = CAST(:v AS vector) WHERE id = :id"
            ),
            {"v": literal, "id": row_id},
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_llm_response_cache_embedding_hnsw "
        "ON llm_response_cache USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_llm_response_cache_embedding_hnsw")
    op.execute("ALTER TABLE llm_response_cache DROP COLUMN IF EXISTS embedding")
    # The extension is intentionally left installed (other consumers may
    # depend on it; dropping it is a DBA decision, not a migration's).
