"""add sponsors table for editorial sponsor slot (BUILD.md step 3)

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-05-08

Editorial sponsor banner between Tonight and This week on /home. Distinct
from `Provider.tier` / `sponsored_until` / `featured_description` (which
back the business spotlight monetization, BUILD.md "Spotlight architecture").

A sponsor is whoever paid for the editorial slot — could be a real estate
agency, a tour operator, a brand without a Provider record at all. Hence
its own table.

Schema mirrors BUILD.md "Sponsor slot architecture":

  id          uuid (string)
  name        "Havasu Outdoor Co."
  eyebrow     "Local sponsor · on the water"
  line        short blurb under the name
  cta_label   "Reserve"
  cta_url     "https://example.com"
  image_url   nullable (placeholder gradient when null)
  starts_at   nullable (always-on when null)
  ends_at     nullable (no end when null)
  active      bool — admin kill switch independent of dates
  weight      int — for rotation when multiple are simultaneously active
  created_at  bookkeeping
  updated_at  bookkeeping
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sponsors",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("eyebrow", sa.String(255), nullable=True),
        sa.Column("line", sa.Text(), nullable=True),
        sa.Column("cta_label", sa.String(64), nullable=False, server_default="Visit"),
        sa.Column("cta_url", sa.String(2048), nullable=False),
        sa.Column("image_url", sa.String(2048), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Speeds up the active-sponsor lookup on every /home render. The
    # query filters on (active, starts_at, ends_at) and orders by weight.
    op.create_index(
        "ix_sponsors_active_window",
        "sponsors",
        ["active", "starts_at", "ends_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sponsors_active_window", table_name="sponsors")
    op.drop_table("sponsors")
