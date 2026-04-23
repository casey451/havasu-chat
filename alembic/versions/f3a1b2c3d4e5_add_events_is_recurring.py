"""add events.is_recurring (Phase 8.9)

Revision ID: f3a1b2c3d4e5
Revises: a8f2c1d0e1ab
Create Date: 2026-04-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "a8f2c1d0e1ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column(
            "is_recurring",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("events", "is_recurring")
