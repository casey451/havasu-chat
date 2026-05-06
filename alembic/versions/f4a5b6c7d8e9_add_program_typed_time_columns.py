"""add program typed time columns + python backfill (Slice 53, Backlog #30)

Adds nullable ``schedule_start_time_typed`` / ``schedule_end_time_typed``
(``Time``) columns to ``programs`` alongside the existing
``schedule_start_time`` / ``schedule_end_time`` ``String(5)`` columns. Backfills
existing rows by parsing the ``HH:MM`` strings in Python (cross-dialect: SQLite
and Postgres parse the same way through ``datetime.time.fromisoformat``).

The ORM ``@validates`` decorator on ``Program`` keeps the typed columns in sync
at every ORM writer going forward; this migration only handles existing rows.
Slice 56 will drop the string columns and rename the typed columns to the
canonical names (``schedule_start_time`` / ``schedule_end_time``) so reader
code that uses ``program.schedule_start_time`` keeps working unchanged — it
just receives a ``time`` object instead of a ``str``.

Revision ID: f4a5b6c7d8e9
Revises: 7d8c9e0f1a2b
Create Date: 2026-05-05

"""

from datetime import time
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import bindparam, text

from alembic import op

revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "7d8c9e0f1a2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "programs",
        sa.Column("schedule_start_time_typed", sa.Time(), nullable=True),
    )
    op.add_column(
        "programs",
        sa.Column("schedule_end_time_typed", sa.Time(), nullable=True),
    )

    bind = op.get_bind()
    rows = bind.execute(
        text(
            "SELECT id, schedule_start_time, schedule_end_time FROM programs"
        )
    ).fetchall()

    # Bind ``:st`` / ``:et`` with explicit ``Time()`` type so SQLAlchemy applies the
    # right dialect adapter (SQLite's stdlib sqlite3 driver does not natively bind
    # ``datetime.time`` values; Postgres' psycopg2 does). Without bindparam typing,
    # SQLite raises ``ProgrammingError: type 'datetime.time' is not supported``.
    update_stmt = text(
        "UPDATE programs SET schedule_start_time_typed = :st, "
        "schedule_end_time_typed = :et WHERE id = :id"
    ).bindparams(
        bindparam("st", type_=sa.Time()),
        bindparam("et", type_=sa.Time()),
    )
    for row_id, st_str, et_str in rows:
        try:
            st_val = time.fromisoformat(st_str) if st_str else None
        except ValueError:
            st_val = None
        try:
            et_val = time.fromisoformat(et_str) if et_str else None
        except ValueError:
            et_val = None
        bind.execute(update_stmt, {"st": st_val, "et": et_val, "id": row_id})


def downgrade() -> None:
    op.drop_column("programs", "schedule_end_time_typed")
    op.drop_column("programs", "schedule_start_time_typed")
