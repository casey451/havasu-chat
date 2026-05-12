"""Phase 2B.2 — Postgres FTS on ``entities.search_vector`` + pg_trgm indexes.

Revision ID: c8d9e0f1a2b3
Revises: 92ce4899dc08
Create Date: 2026-05-12

Postgres-only DDL (dialect-gated). SQLite test/dev upgrades skip silently so
Alembic ``upgrade head`` stays green without ``tsvector`` support.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "92ce4899dc08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite: no tsvector / GIN / pg_trgm — tier2 uses ILIKE fallback (Phase 2B.2 brief §9).
        return
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    op.execute(
        sa.text(
            "ALTER TABLE entities ADD COLUMN search_vector tsvector "
            "GENERATED ALWAYS AS ("
            "setweight(to_tsvector('english', coalesce(name, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(description, '')), 'B')"
            ") STORED"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX ix_entities_search_vector ON entities USING gin (search_vector)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX ix_entities_name_trgm ON entities USING gin (name gin_trgm_ops)"
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX ix_providers_emergency_service
              ON providers ((attributes ->> 'emergency_service'))
              WHERE attributes ->> 'emergency_service' = 'true'
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX ix_providers_dog_friendly
              ON providers ((attributes ->> 'dog_friendly'))
              WHERE attributes ->> 'dog_friendly' = 'true'
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(sa.text("DROP INDEX IF EXISTS ix_providers_dog_friendly"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_providers_emergency_service"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_entities_name_trgm"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_entities_search_vector"))
    op.execute(sa.text("ALTER TABLE entities DROP COLUMN IF EXISTS search_vector"))
