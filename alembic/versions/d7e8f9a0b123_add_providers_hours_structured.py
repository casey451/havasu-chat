"""add providers.hours_structured JSON (Phase 5.6)

Revision ID: d7e8f9a0b123
Revises: c6d7e8f9a012
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7e8f9a0b123"
down_revision: Union[str, Sequence[str], None] = "c6d7e8f9a012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("providers", sa.Column("hours_structured", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("providers", "hours_structured")
