"""chat_logs: columns for unified router analytics (Phase 2.2)

Revision ID: f1a2b3c4d506
Revises: e8a1c2d3e404
Create Date: 2026-04-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d506"
down_revision: Union[str, Sequence[str], None] = "e8a1c2d3e404"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chat_logs", sa.Column("query_text_hashed", sa.String(length=128), nullable=True))
    op.add_column("chat_logs", sa.Column("normalized_query", sa.Text(), nullable=True))
    op.add_column("chat_logs", sa.Column("mode", sa.String(length=32), nullable=True))
    op.add_column("chat_logs", sa.Column("sub_intent", sa.String(length=64), nullable=True))
    op.add_column("chat_logs", sa.Column("entity_matched", sa.String(length=512), nullable=True))
    op.add_column("chat_logs", sa.Column("tier_used", sa.String(length=32), nullable=True))
    op.add_column("chat_logs", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.add_column("chat_logs", sa.Column("llm_tokens_used", sa.Integer(), nullable=True))
    op.add_column("chat_logs", sa.Column("feedback_signal", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_logs", "feedback_signal")
    op.drop_column("chat_logs", "llm_tokens_used")
    op.drop_column("chat_logs", "latency_ms")
    op.drop_column("chat_logs", "tier_used")
    op.drop_column("chat_logs", "entity_matched")
    op.drop_column("chat_logs", "sub_intent")
    op.drop_column("chat_logs", "mode")
    op.drop_column("chat_logs", "normalized_query")
    op.drop_column("chat_logs", "query_text_hashed")
