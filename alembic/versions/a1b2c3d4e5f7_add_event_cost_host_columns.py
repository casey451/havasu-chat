"""Add events.cost, events.cost_description, events.host (event data fixes 2.2 / 4.3).

Purely additive: three nullable columns on ``events``; fully reversible. The
shared field contract for the 2026-06 event data-quality pass also includes
``events.image_url`` — that column already exists (migration ``c7e8f9a0b1c2``),
so it is intentionally NOT re-added here.

  * ``cost`` (String, nullable)             — short human price label: "$20" / "Free" / "$10-$25"
  * ``cost_description`` (Text, nullable)   — extra pricing notes ("members $15")
  * ``host`` (String, nullable)             — instructor/host name extracted from a class title

Mirrors how the Program model exposes ``cost`` / ``cost_description``. Populated
on ingest (app/contrib/event_ingest.py) and by
scripts/backfill_event_fields_2026_06.py. Rendering is owned by other lanes.

Revision ID: a1b2c3d4e5f7
Revises: iav2struct1
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "iav2struct1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("cost", sa.String(), nullable=True))
    op.add_column("events", sa.Column("cost_description", sa.Text(), nullable=True))
    op.add_column("events", sa.Column("host", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "host")
    op.drop_column("events", "cost_description")
    op.drop_column("events", "cost")
