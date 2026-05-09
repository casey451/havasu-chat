"""evolve sponsors for four-tier inventory + moderation pipeline (Phase 2B)

Revision ID: 2a3b4c5d6e7f
Revises: 1a2b3c4d5e6f
Create Date: 2026-05-08

Phase 2B of the home-page redesign (see CRITIQUE_AND_REDESIGN.md §B5.6 + §C11c).
Evolves the existing single-slot ``sponsors`` table (added in e3f4a5b6c7d8) into
a four-tier ad inventory (Marquee / Spotlight / Promoted / Supporters wall) with
a draft → review → approved → live → paused → archived state machine.

Backwards compatible: existing rows are defaulted to ``slot='marquee'`` and
``status='approved'`` so the live-record query in ``sponsor_store`` continues
to return them. The legacy ``active`` boolean is kept as an admin kill-switch
that overrides the state machine (an emergency takedown does not require an
admin to walk the row through ``paused`` first).

Migration design — plain ALTER, no batch mode:

This migration uses plain ``op.add_column`` calls rather than batch mode. SQLite
supports ``ALTER TABLE ADD COLUMN`` for nullable columns and columns with
``server_default``, which covers every column added here. We deliberately do
NOT add a FK constraint on ``business_id`` even though it logically references
``providers.id`` — adding the FK would force ``batch_alter_table`` mode under
SQLite, and alembic's batch mode hits a topological-sort edge case when adding
12 columns at once that raises a spurious ``CircularDependencyError``. The
sponsor → provider relationship is enforced at the application layer instead;
``sponsor_store.py`` validates the relationship on insert and the admin UI
constrains business_id selection to existing providers. If we ever need DB-
level enforcement, a follow-up migration on Postgres-only can add it.

New columns:

* ``slot``               — AdSlot enum: marquee / spotlight / promoted / supporter
* ``status``             — SponsorStatus FSM: draft / review / approved / live /
                           paused / archived
* ``headline``           — advertiser-written catchy line (Marquee), nullable
* ``pitch``              — longer one-line pitch, nullable
* ``attribution_text``   — "Sponsored by [Business name]" line, nullable
* ``paused_at``          — when an admin paused the sponsor, nullable
* ``paused_reason``      — short admin note for why, nullable
* ``impressions``        — server-side render count, default 0
* ``clicks``             — count via /sponsor/click attribution endpoint, default 0
* ``approved_at``        — when the moderation approval landed, nullable
* ``approved_by``        — admin user identifier for the approval, nullable
* ``business_id``        — optional Provider id (no DB-level FK; enforced in app)

Index ``ix_sponsors_slot_status`` accelerates the per-slot active lookup that
runs on every /home render.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "2a3b4c5d6e7f"
down_revision: Union[str, Sequence[str], None] = "1a2b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sponsors",
        sa.Column("slot", sa.String(32), nullable=False, server_default="marquee"),
    )
    op.add_column(
        "sponsors",
        sa.Column("status", sa.String(32), nullable=False, server_default="approved"),
    )
    op.add_column("sponsors", sa.Column("headline", sa.String(255), nullable=True))
    op.add_column("sponsors", sa.Column("pitch", sa.Text(), nullable=True))
    op.add_column("sponsors", sa.Column("attribution_text", sa.String(255), nullable=True))
    op.add_column("sponsors", sa.Column("paused_at", sa.DateTime(), nullable=True))
    op.add_column("sponsors", sa.Column("paused_reason", sa.String(255), nullable=True))
    op.add_column(
        "sponsors",
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "sponsors",
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("sponsors", sa.Column("approved_at", sa.DateTime(), nullable=True))
    op.add_column("sponsors", sa.Column("approved_by", sa.String(255), nullable=True))
    op.add_column("sponsors", sa.Column("business_id", sa.Integer(), nullable=True))

    # Hot-path index — ``slot``+``status`` filter runs on every /home render.
    op.create_index(
        "ix_sponsors_slot_status",
        "sponsors",
        ["slot", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_sponsors_slot_status", table_name="sponsors")
    op.drop_column("sponsors", "business_id")
    op.drop_column("sponsors", "approved_by")
    op.drop_column("sponsors", "approved_at")
    op.drop_column("sponsors", "clicks")
    op.drop_column("sponsors", "impressions")
    op.drop_column("sponsors", "paused_reason")
    op.drop_column("sponsors", "paused_at")
    op.drop_column("sponsors", "attribution_text")
    op.drop_column("sponsors", "pitch")
    op.drop_column("sponsors", "headline")
    op.drop_column("sponsors", "status")
    op.drop_column("sponsors", "slot")
