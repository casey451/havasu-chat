"""Phase 1B — backfill Provider/Event/Program into ENTITY + extensions.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-14

Adds nullable ``entity_id`` FK on legacy catalog tables, runs Python backfill
(idempotent — skips rows that already have ``entity_id``), updates sponsor
discriminator, leaves ``entity_id`` nullable so inserts remain valid with zero
app-layer changes until Phase 1D dual-write.

Implementation lives in ``app.db.entity_backfill.run_entity_backfill``.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("entity_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_providers_entity_id",
            "entities",
            ["entity_id"],
            ["id"],
        )
    op.create_index("ix_providers_entity_id", "providers", ["entity_id"])

    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("entity_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_events_entity_id",
            "entities",
            ["entity_id"],
            ["id"],
        )
    op.create_index("ix_events_entity_id", "events", ["entity_id"])

    with op.batch_alter_table("programs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("entity_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_programs_entity_id",
            "entities",
            ["entity_id"],
            ["id"],
        )
    op.create_index("ix_programs_entity_id", "programs", ["entity_id"])

    conn = op.get_bind()
    from app.db.entity_backfill import run_entity_backfill

    run_entity_backfill(conn)


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("UPDATE sponsors SET entity_type = NULL WHERE entity_type = 'commercial'"))
    conn.execute(text("UPDATE providers SET entity_id = NULL"))
    conn.execute(text("UPDATE events SET entity_id = NULL"))
    conn.execute(text("UPDATE programs SET entity_id = NULL"))
    if conn.dialect.name == "sqlite":
        conn.execute(text("PRAGMA foreign_keys=ON"))
    # Mirror Phase 1A extension dependency order — SQLite batch parity.
    for tbl in (
        "sponsorship_slots",
        "source_evidence",
        "schedules",
        "service_areas",
        "offerings",
        "features",
        "contact_points",
        "seasonal_hours",
        "hours",
        "locations",
        "entity_categories",
    ):
        conn.execute(text(f"DELETE FROM {tbl}"))
    conn.execute(text("DELETE FROM entities"))

    op.drop_index("ix_programs_entity_id", table_name="programs")
    with op.batch_alter_table("programs", schema=None) as batch_op:
        batch_op.drop_constraint("fk_programs_entity_id", type_="foreignkey")
        batch_op.drop_column("entity_id")

    op.drop_index("ix_events_entity_id", table_name="events")
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.drop_constraint("fk_events_entity_id", type_="foreignkey")
        batch_op.drop_column("entity_id")

    op.drop_index("ix_providers_entity_id", table_name="providers")
    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.drop_constraint("fk_providers_entity_id", type_="foreignkey")
        batch_op.drop_column("entity_id")
