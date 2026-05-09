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

SQLite compatibility note: this migration uses ``batch_alter_table`` so it
applies cleanly under SQLite (which cannot ``ALTER TABLE ADD COLUMN`` for a
foreign key). Postgres treats batch mode as a no-op and runs the same DDL.

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
* ``business_id``        — optional FK to providers; null for external advertisers

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
    # Use batch mode so SQLite can add the FK column. Postgres treats this as
    # a normal ALTER. All column additions ride in the same batch transaction
    # so a partial failure doesn't leave the table half-evolved.
    with op.batch_alter_table("sponsors", recreate="auto") as batch:
        batch.add_column(
            sa.Column("slot", sa.String(32), nullable=False, server_default="marquee")
        )
        batch.add_column(
            sa.Column("status", sa.String(32), nullable=False, server_default="approved")
        )
        batch.add_column(sa.Column("headline", sa.String(255), nullable=True))
        batch.add_column(sa.Column("pitch", sa.Text(), nullable=True))
        batch.add_column(sa.Column("attribution_text", sa.String(255), nullable=True))
        batch.add_column(sa.Column("paused_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("paused_reason", sa.String(255), nullable=True))
        batch.add_column(
            sa.Column("impressions", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("clicks", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("approved_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("approved_by", sa.String(255), nullable=True))
        batch.add_column(sa.Column("business_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_sponsors_business_id_providers",
            "providers",
            ["business_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Hot-path index — ``slot``+``status`` filter runs on every /home render.
    op.create_index(
        "ix_sponsors_slot_status",
        "sponsors",
        ["slot", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_sponsors_slot_status", table_name="sponsors")
    with op.batch_alter_table("sponsors", recreate="auto") as batch:
        batch.drop_constraint("fk_sponsors_business_id_providers", type_="foreignkey")
        batch.drop_column("business_id")
        batch.drop_column("approved_by")
        batch.drop_column("approved_at")
        batch.drop_column("clicks")
        batch.drop_column("impressions")
        batch.drop_column("paused_reason")
        batch.drop_column("paused_at")
        batch.drop_column("attribution_text")
        batch.drop_column("pitch")
        batch.drop_column("headline")
        batch.drop_column("status")
        batch.drop_column("slot")
