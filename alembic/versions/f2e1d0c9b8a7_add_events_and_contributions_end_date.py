"""add end_date to events and event_end_date to contributions (multi-day events)

Revision ID: f2e1d0c9b8a7
Revises: d1e2f3a4b567
Create Date: 2026-04-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2e1d0c9b8a7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b567"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("end_date", sa.Date(), nullable=True))
    op.add_column("contributions", sa.Column("event_end_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("contributions", "event_end_date")
    op.drop_column("events", "end_date")
