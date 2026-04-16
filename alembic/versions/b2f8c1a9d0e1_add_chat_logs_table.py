"""add chat_logs table

Revision ID: b2f8c1a9d0e1
Revises: 54d37d2c4d32
Create Date: 2026-04-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2f8c1a9d0e1"
down_revision: Union[str, Sequence[str], None] = "54d37d2c4d32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_logs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("intent", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_logs_session_id", "chat_logs", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chat_logs_session_id", table_name="chat_logs")
    op.drop_table("chat_logs")
