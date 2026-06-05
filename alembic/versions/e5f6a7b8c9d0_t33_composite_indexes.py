"""T3.3 — composite indexes for hot filters (audit P4).

Hot query paths verified in the 2026-06-04 audit run WITHOUT composite
indexes:

- ``providers`` filtered by ``(entity_id, is_active, draft)`` — the provider
  resolution every card/profile/map surface does.
- ``events`` filtered by ``(date, entity_id)`` — dedup candidate selection and
  the venue-events region.

CASEY GATE: this is a prod schema change. Merging to main applies it via the
Railway preDeploy ``alembic upgrade head``. Index creation on these table
sizes (thousands of rows) is sub-second on Postgres; still, merge knowingly.

Revision ID: e5f6a7b8c9d0
Revises: c1d2e3f4a5b6
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_index(
        "ix_providers_entity_active_draft",
        "providers",
        ["entity_id", "is_active", "draft"],
    )
    op.create_index(
        "ix_events_date_entity",
        "events",
        ["date", "entity_id"],
    )

def downgrade() -> None:
    op.drop_index("ix_events_date_entity", table_name="events")
    op.drop_index("ix_providers_entity_active_draft", table_name="providers")
