"""drop programs schedule_*_time strings + rename typed -> canonical (Slice 56)

Terminal migration of the schema time-type harmonization campaign
(Backlog #30 — Option B, decision doc §5).

This migration:
  - Aborts if any program row has NULL schedule_*_time_typed (Slice 53's
    backfill should have left zero NULLs; defensive pre-flight before any
    structural change).
  - Drops Program.schedule_start_time / schedule_end_time (String(5)).
  - Renames Program.schedule_start_time_typed -> schedule_start_time
    and Program.schedule_end_time_typed -> schedule_end_time.
  - The renamed columns retain their Time type and become NOT NULL
    (matches the model's new mapping).

After this migration, the canonical column name (schedule_start_time) holds
a Time value; the string column is gone; the dual-write @validates decorator
is removed in the same commit (model edit). Pydantic
ProgramBase.parse_hhmm(mode='before') absorbs the HH:MM-string -> time
conversion at the schema boundary.

The downgrade restores the post-Slice-53 state (string columns + typed
columns, both populated). batch_alter_table is used for both directions so
SQLite and Postgres apply the DDL the same way.

Revision ID: a7b8c9d0e1f2
Revises: f4a5b6c7d8e9
Create Date: 2026-05-05

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Pre-flight: every typed column must be NOT NULL before we promote it
    # to the canonical (NOT NULL) position. Slice 53's backfill should have
    # left zero NULLs; verify defensively. If any row has NULL, halt cleanly
    # rather than dropping data with NULL replacements.
    bind = op.get_bind()
    null_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM programs "
            "WHERE schedule_start_time_typed IS NULL "
            "   OR schedule_end_time_typed IS NULL"
        )
    ).scalar()
    if null_count and null_count > 0:
        raise RuntimeError(
            f"Slice 56 migration aborted: {null_count} programs row(s) "
            "have NULL schedule_*_time_typed. Slice 53 backfill missed "
            "these rows; investigate and re-backfill before re-running. "
            "See relay/slice_56_drop_strings_rename_canonical.md Step 7 "
            "for the manual re-backfill recipe."
        )

    # SQLite native ALTER COLUMN is not supported; batch_alter_table is the
    # cross-dialect way to drop columns and rename columns. Postgres handles
    # these directly inside the batch context too.
    with op.batch_alter_table("programs") as batch:
        batch.drop_column("schedule_start_time")
        batch.drop_column("schedule_end_time")
        batch.alter_column(
            "schedule_start_time_typed",
            new_column_name="schedule_start_time",
            existing_type=sa.Time(),
            nullable=False,
        )
        batch.alter_column(
            "schedule_end_time_typed",
            new_column_name="schedule_end_time",
            existing_type=sa.Time(),
            nullable=False,
        )


def downgrade() -> None:
    # Reverse path: rename canonical Time columns back to *_typed (still Time,
    # nullable=True), re-add String(5) columns (nullable=True so the table is
    # bootable mid-downgrade), backfill strings from typed via strftime, then
    # tighten string columns to NOT NULL to match the post-Slice-53 schema.
    with op.batch_alter_table("programs") as batch:
        batch.alter_column(
            "schedule_start_time",
            new_column_name="schedule_start_time_typed",
            existing_type=sa.Time(),
            nullable=True,
        )
        batch.alter_column(
            "schedule_end_time",
            new_column_name="schedule_end_time_typed",
            existing_type=sa.Time(),
            nullable=True,
        )
        batch.add_column(sa.Column("schedule_start_time", sa.String(length=5), nullable=True))
        batch.add_column(sa.Column("schedule_end_time", sa.String(length=5), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, schedule_start_time_typed, schedule_end_time_typed FROM programs"
        )
    ).fetchall()
    for row_id, st_typed, et_typed in rows:
        start_s = st_typed.strftime("%H:%M") if st_typed is not None else None
        end_s = et_typed.strftime("%H:%M") if et_typed is not None else None
        bind.execute(
            sa.text(
                "UPDATE programs SET schedule_start_time = :s, "
                "schedule_end_time = :e WHERE id = :id"
            ),
            {"s": start_s, "e": end_s, "id": row_id},
        )

    # Restore NOT NULL on the strings (matches post-Slice-53 schema).
    with op.batch_alter_table("programs") as batch:
        batch.alter_column(
            "schedule_start_time", existing_type=sa.String(length=5), nullable=False
        )
        batch.alter_column(
            "schedule_end_time", existing_type=sa.String(length=5), nullable=False
        )
