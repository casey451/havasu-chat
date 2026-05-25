"""Lane B-3: chat_logs cache_status + timing_ms observability columns.

Revision ID: acc50395da86
Revises: a9b0c1d2e3f4
Create Date: 2026-05-24

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "acc50395da86"
down_revision: Union[str, Sequence[str], None] = "a9b0c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_logs",
        sa.Column("cache_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "chat_logs",
        sa.Column("timing_ms", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_logs", "timing_ms")
    op.drop_column("chat_logs", "cache_status")
