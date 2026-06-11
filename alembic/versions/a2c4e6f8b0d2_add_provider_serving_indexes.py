"""add provider serving indexes (audit C1/C2/H4)

Partial indexes matching the live serving predicate (``is_active AND NOT draft``)
for the category / home / spotlight Provider filters, which previously fell to
sequential scans on the busiest pages:
  - providers.category            (legacy column, previously UNindexed)
  - providers.primary_category    (partial composite with the serving predicate)
  - providers.subcategory         (partial composite with the serving predicate)
  - providers.(tier, sponsored_until)  (spotlight / sponsor filter on /home)

On PostgreSQL the indexes are created CONCURRENTLY (no table-write lock) and
idempotently (IF NOT EXISTS) inside an autocommit block. On SQLite (the test /
local path ``init_db`` runs via ``alembic upgrade head``) plain indexes are
created, since SQLite supports neither CONCURRENTLY nor the boolean partial
predicate the same way.

NOTE: ``primary_category`` / ``subcategory`` already have plain single-column
indexes; these partials match the exact serving predicate and may let you drop
the plain ones in a follow-up. ``category`` and ``(tier, sponsored_until)`` were
uncovered.

down_revision = current head ``d4e5f6a7b8c9`` (computed 2026-06-11). If a newer
migration has landed, re-point down_revision at the real head.
"""

from __future__ import annotations

from alembic import op

revision: str = "a2c4e6f8b0d2"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None

# (index_name, postgres_column_sql, sqlite_columns)
_INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    ("ix_providers_category_live", "(category)", ["category"]),
    ("ix_providers_primary_category_live", "(primary_category)", ["primary_category"]),
    ("ix_providers_subcategory_live", "(subcategory)", ["subcategory"]),
    ("ix_providers_tier_sponsored_live", "(tier, sponsored_until)", ["tier", "sponsored_until"]),
)

_PG_PREDICATE = "WHERE is_active AND NOT draft"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # CONCURRENTLY must run outside a transaction; autocommit_block provides
        # that. IF NOT EXISTS keeps a retried deploy idempotent.
        with op.get_context().autocommit_block():
            for name, cols_sql, _ in _INDEXES:
                op.execute(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
                    f"ON providers {cols_sql} {_PG_PREDICATE}"
                )
    else:
        for name, _, cols in _INDEXES:
            op.create_index(name, "providers", cols, unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            for name, _, _ in reversed(_INDEXES):
                op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
    else:
        for name, _, _ in reversed(_INDEXES):
            op.drop_index(name, table_name="providers")
