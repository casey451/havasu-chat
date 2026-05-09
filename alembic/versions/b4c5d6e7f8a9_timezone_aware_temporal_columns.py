"""timezone-aware temporal columns (Backlog #41 / Lane S1.1)

Alters four nullable datetime columns from naive ``DateTime`` to
``DateTime(timezone=True)``:

* ``providers.last_verified_at``
* ``events.last_verified_at``
* ``sponsors.starts_at``, ``sponsors.ends_at``

Postgres stores ``TIMESTAMP WITH TIME ZONE``; SQLite behavior is unchanged at the
storage layer but SQLAlchemy returns timezone-aware datetimes from the ORM.

Existing application timestamps are written as aware values
(``now_lake_havasu()`` / ``datetime.now(UTC)``). On Postgres, naive stored
values are interpreted as UTC via ``AT TIME ZONE 'UTC'`` in the ``USING``
clause.

Revision ID: b4c5d6e7f8a9
Revises: f7e8d9c0b1a2
Create Date: 2026-05-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = "f7e8d9c0b1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DT_NAIVE = sa.DateTime()
_DT_TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    # Postgres: TIMESTAMP → TIMESTAMPTZ; naive values treated as UTC.
    _pg_using_in = "last_verified_at AT TIME ZONE 'UTC'"
    _pg_using_starts = "starts_at AT TIME ZONE 'UTC'"
    _pg_using_ends = "ends_at AT TIME ZONE 'UTC'"

    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.alter_column(
            "last_verified_at",
            existing_type=_DT_NAIVE,
            type_=_DT_TZ,
            existing_nullable=True,
            postgresql_using=_pg_using_in,
        )

    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.alter_column(
            "last_verified_at",
            existing_type=_DT_NAIVE,
            type_=_DT_TZ,
            existing_nullable=True,
            postgresql_using=_pg_using_in,
        )

    with op.batch_alter_table("sponsors", schema=None) as batch_op:
        batch_op.alter_column(
            "starts_at",
            existing_type=_DT_NAIVE,
            type_=_DT_TZ,
            existing_nullable=True,
            postgresql_using=_pg_using_starts,
        )
        batch_op.alter_column(
            "ends_at",
            existing_type=_DT_NAIVE,
            type_=_DT_TZ,
            existing_nullable=True,
            postgresql_using=_pg_using_ends,
        )


def downgrade() -> None:
    _pg_using_rev_in = "last_verified_at AT TIME ZONE 'UTC'"
    _pg_using_rev_starts = "starts_at AT TIME ZONE 'UTC'"
    _pg_using_rev_ends = "ends_at AT TIME ZONE 'UTC'"

    with op.batch_alter_table("sponsors", schema=None) as batch_op:
        batch_op.alter_column(
            "ends_at",
            existing_type=_DT_TZ,
            type_=_DT_NAIVE,
            existing_nullable=True,
            postgresql_using=_pg_using_rev_ends,
        )
        batch_op.alter_column(
            "starts_at",
            existing_type=_DT_TZ,
            type_=_DT_NAIVE,
            existing_nullable=True,
            postgresql_using=_pg_using_rev_starts,
        )

    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.alter_column(
            "last_verified_at",
            existing_type=_DT_TZ,
            type_=_DT_NAIVE,
            existing_nullable=True,
            postgresql_using=_pg_using_rev_in,
        )

    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.alter_column(
            "last_verified_at",
            existing_type=_DT_TZ,
            type_=_DT_NAIVE,
            existing_nullable=True,
            postgresql_using=_pg_using_rev_in,
        )
