"""add source_url column to contributions and events

Revision ID: 7d8c9e0f1a2b
Revises: f2e1d0c9b8a7
Create Date: 2026-04-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7d8c9e0f1a2b"
down_revision: Union[str, Sequence[str], None] = "f2e1d0c9b8a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "contributions",
        sa.Column("source_url", sa.String(length=2048), nullable=True),
    )
    op.create_index(
        "ix_contributions_source_url",
        "contributions",
        ["source_url"],
        unique=False,
    )
    op.add_column(
        "events",
        sa.Column("source_url", sa.String(length=2048), nullable=True),
    )
    op.create_index(
        "ix_events_source_url",
        "events",
        ["source_url"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_events_source_url", table_name="events")
    op.drop_column("events", "source_url")
    op.drop_index("ix_contributions_source_url", table_name="contributions")
    op.drop_column("contributions", "source_url")
