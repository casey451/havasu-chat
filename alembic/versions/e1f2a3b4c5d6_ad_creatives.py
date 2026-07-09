"""Phase F2: ad_creatives (merchant ad creative model)

Revision ID: f2adcr8a9b0c
Revises: b7c1f2a3d4e5
Create Date: 2026-06-14

(NOTE: filename still reads e1f2a3b4c5d6_ad_creatives.py — that id was already
taken by phase3_data_pass, so the revision id below was corrected to a unique
value. Optional cleanup: ``git mv`` this file to f2adcr8a9b0c_ad_creatives.py.)

Additive only — one NEW table. ``placements.creative_id`` already exists (added
in b7c1f2a3d4e5) and references a row here by id; no DB-level FK is added so this
stays a pure create-table with no change to any existing table.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2adcr8a9b0c"
down_revision: Union[str, Sequence[str], None] = "b7c1f2a3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ad_creatives",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "provider_id", sa.String(),
            sa.ForeignKey("providers.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("headline", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("cta_label", sa.String(length=80), nullable=True),
        sa.Column("cta_url", sa.String(length=512), nullable=True),
        sa.Column("image_url", sa.String(length=512), nullable=True),
        sa.Column("image_url_mobile", sa.String(length=512), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ad_creatives_provider_id", "ad_creatives", ["provider_id"])


def downgrade() -> None:
    op.drop_index("ix_ad_creatives_provider_id", table_name="ad_creatives")
    op.drop_table("ad_creatives")
