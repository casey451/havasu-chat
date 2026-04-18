"""add programs table

Revision ID: c3a9e2f5b801
Revises: b2f8c1a9d0e1
Create Date: 2026-04-17

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3a9e2f5b801"
down_revision: Union[str, Sequence[str], None] = "b2f8c1a9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "programs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("activity_category", sa.String(), nullable=False),
        sa.Column("age_min", sa.Integer(), nullable=True),
        sa.Column("age_max", sa.Integer(), nullable=True),
        sa.Column("schedule_days", sa.JSON(), nullable=False),
        sa.Column("schedule_start_time", sa.String(length=5), nullable=False),
        sa.Column("schedule_end_time", sa.String(length=5), nullable=False),
        sa.Column("location_name", sa.String(), nullable=False),
        sa.Column("location_address", sa.String(), nullable=True),
        sa.Column("cost", sa.String(), nullable=True),
        sa.Column("provider_name", sa.String(), nullable=False),
        sa.Column("contact_phone", sa.String(length=64), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_url", sa.String(length=2048), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("programs")
