"""Master spec §3.8: ad_slots schema only (not wired in v1).

Revision ID: v1b2c3d4e5f7
Revises: v1a2b3c4d5e6
Create Date: 2026-05-31
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "v1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "v1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ad_slots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("business_id", sa.String(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("tier", sa.String(length=32), nullable=True),
        sa.Column("position", sa.String(length=32), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ad_slots_business_id", "ad_slots", ["business_id"])
    op.create_index("ix_ad_slots_active", "ad_slots", ["active"])


def downgrade() -> None:
    op.drop_index("ix_ad_slots_active", table_name="ad_slots")
    op.drop_index("ix_ad_slots_business_id", table_name="ad_slots")
    op.drop_table("ad_slots")
