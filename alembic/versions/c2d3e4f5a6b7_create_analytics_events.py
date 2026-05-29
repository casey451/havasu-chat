"""create analytics_events table (v54 Track B — spotlight + chat-card telemetry)

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-05-29

v54 Track B follows the v52 sponsor counter pattern (atomic per-render writes
landed for Sponsor.impressions / Sponsor.clicks in PR #44 / PR #53). Those
two counters answer "is this slot performing?" but they can't answer
"which slot, which rank, which surface?". analytics_events is the long
form: one row per render, one row per click, one row per chat-card
surface render.

Schema:

  id              uuid string (matches Sponsor / Provider PK convention —
                  models.py uses ``default=lambda: str(uuid4())`` for
                  Sponsor.id and Provider.id; new analytics rows do the same
                  so the table joins cleanly to either side)
  event_name      "home.spotlight.impression" / "home.spotlight.click" /
                  "home.sponsor.click" / "chat.card_row.impression" /
                  "chat.single_card.open"
  slot            "marquee" / "spotlight" / "promoted" / "supporter" / null
  sponsor_id      FK sponsors.id (SET NULL on delete — analytics outlives
                  the sponsor row; we don't want a takedown to nuke
                  historical CTR)
  provider_id     FK providers.id (SET NULL — same reasoning)
  ranking_score   integer; mirrors Sponsor.weight (Integer in models.py
                  line 599) at emit time so downstream CTR-by-rank math
                  doesn't have to re-join to a possibly-mutated row
  slot_origin     string — chat-side surface tag ("tier2_card_row" /
                  "tier2_single_card"). Distinct from ``slot``: ``slot``
                  is sponsor inventory; ``slot_origin`` is render surface.
  payload_json    JSON catch-all so future fields can land without a
                  migration
  created_at      timestamp, indexed (every read path is "events in the
                  last N hours" or "events for sponsor X over time")
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("event_name", sa.String(length=128), nullable=False),
        sa.Column("slot", sa.String(length=32), nullable=True),
        sa.Column(
            "sponsor_id",
            sa.String(),
            sa.ForeignKey("sponsors.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "provider_id",
            sa.String(),
            sa.ForeignKey("providers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("ranking_score", sa.Integer(), nullable=True),
        sa.Column("slot_origin", sa.String(length=64), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_analytics_events_event_name",
        "analytics_events",
        ["event_name"],
    )
    op.create_index(
        "ix_analytics_events_created_at",
        "analytics_events",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_events_created_at", table_name="analytics_events")
    op.drop_index("ix_analytics_events_event_name", table_name="analytics_events")
    op.drop_table("analytics_events")
