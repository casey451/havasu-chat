"""normalize JSON null embedding values to SQL NULL (Phase 8.11c-fix)

ORM models use ``JSON(none_as_null=True)`` so ``None`` persists as SQL NULL.
This migration fixes any existing rows where JSON ``null`` was stored as the
literal (so ``IS NULL`` filters work).

Revision ID: d1e2f3a4b567
Revises: b8c9d0e1f2a3
Create Date: 2026-04-24

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "d1e2f3a4b567"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Convert any JSON `null` literal values to true SQL NULL. Safe no-op if no rows match.
    bind = op.get_bind()
    dname = bind.dialect.name
    if dname == "postgresql":
        # Postgres: `embedding` is type json, not jsonb — comparing json to jsonb is invalid.
        # Cast to text and match the literal JSON null text form (same semantics as SQLite branch).
        for table in ("providers", "events"):
            op.execute(
                text(
                    f"UPDATE {table} SET embedding = NULL "
                    f"WHERE embedding::text = 'null'"
                )
            )
    else:
        # SQLite (and other DBs using text-stored JSON): JSON null is often the literal `null`.
        op.execute(
            text("UPDATE providers SET embedding = NULL WHERE embedding = 'null'")
        )
        op.execute(
            text("UPDATE events SET embedding = NULL WHERE embedding = 'null'")
        )


def downgrade() -> None:
    # The type-level change is reversible by reverting the model; there is no
    # DB-level schema to downgrade for ``none_as_null`` on the JSON type.
    pass
