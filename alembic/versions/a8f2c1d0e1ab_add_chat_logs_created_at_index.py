"""add index on chat_logs.created_at (Phase 8.2)

Revision ID: a8f2c1d0e1ab
Revises: d7e8f9a0b123
Create Date: 2026-04-22

"""

from typing import Sequence, Union

from alembic import op

revision: str = "a8f2c1d0e1ab"
down_revision: Union[str, Sequence[str], None] = "d7e8f9a0b123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_chat_logs_created_at", "chat_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chat_logs_created_at", table_name="chat_logs")
