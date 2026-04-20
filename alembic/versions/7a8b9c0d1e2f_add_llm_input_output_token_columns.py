"""chat_logs: llm_input_tokens + llm_output_tokens (Phase 4.3)

Revision ID: 7a8b9c0d1e2f
Revises: f1a2b3c4d506
Create Date: 2026-04-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7a8b9c0d1e2f"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d506"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chat_logs", sa.Column("llm_input_tokens", sa.Integer(), nullable=True))
    op.add_column("chat_logs", sa.Column("llm_output_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_logs", "llm_output_tokens")
    op.drop_column("chat_logs", "llm_input_tokens")
