"""Phase 6 sidecar — ON DELETE SET NULL on contributions.created_event_id FK.

Revision ID: f6a7b8c9d0e1
Revises: 0a1b2c3d4e5f
Create Date: 2026-05-19

The parks-rec-scrapes GitHub Actions cron has failed every scheduled run since
at least Phase 5.3 because ``scripts/parks_rec_prune.py`` hits a Postgres FK
constraint violation deleting stale events still referenced by rows in
``contributions.created_event_id`` (pre-existing carry-over diagnosed in
Phase 5.7 close-out §3, error signature
``psycopg2.errors.ForeignKeyViolation: ... violates foreign key constraint
"contributions_created_event_id_fkey"``).

Recommended fix (option 1 of 3 surfaced in 5.7 close-out): drop the existing
FK (RESTRICT-default since ``b5c6d7e8f901`` declared it anonymously without
``ondelete``) and re-create with ``ON DELETE SET NULL``. Preserves the
contribution row (audit trail) while severing the link to the deleted event.
Least destructive of the 3 options.

Dialect note: ``b5c6d7e8f901_add_contributions_table.py`` created the FK via
unnamed ``sa.ForeignKeyConstraint(["created_event_id"], ["events.id"])``, so
each dialect picked its own name:

- Postgres: auto-named ``contributions_created_event_id_fkey`` (per the
  production error signature).
- SQLite: anonymous in the reflected table; ``op.batch_alter_table`` needs a
  ``naming_convention`` to assign a stable name we can ``drop_constraint`` by.

Branching by dialect inside ``op.batch_alter_table`` keeps both the SQLite
test runner and the Postgres prod deploy correct.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "0a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SQLITE_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}
_PG_FK_NAME = "contributions_created_event_id_fkey"
_SQLITE_FK_NAME = "fk_contributions_created_event_id_events"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.batch_alter_table("contributions", schema=None) as batch_op:
            batch_op.drop_constraint(_PG_FK_NAME, type_="foreignkey")
            batch_op.create_foreign_key(
                _PG_FK_NAME,
                "events",
                ["created_event_id"],
                ["id"],
                ondelete="SET NULL",
            )
    else:
        with op.batch_alter_table(
            "contributions",
            schema=None,
            naming_convention=_SQLITE_NAMING_CONVENTION,
        ) as batch_op:
            batch_op.drop_constraint(_SQLITE_FK_NAME, type_="foreignkey")
            batch_op.create_foreign_key(
                _SQLITE_FK_NAME,
                "events",
                ["created_event_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.batch_alter_table("contributions", schema=None) as batch_op:
            batch_op.drop_constraint(_PG_FK_NAME, type_="foreignkey")
            batch_op.create_foreign_key(
                _PG_FK_NAME,
                "events",
                ["created_event_id"],
                ["id"],
            )
    else:
        with op.batch_alter_table(
            "contributions",
            schema=None,
            naming_convention=_SQLITE_NAMING_CONVENTION,
        ) as batch_op:
            batch_op.drop_constraint(_SQLITE_FK_NAME, type_="foreignkey")
            batch_op.create_foreign_key(
                _SQLITE_FK_NAME,
                "events",
                ["created_event_id"],
                ["id"],
            )
