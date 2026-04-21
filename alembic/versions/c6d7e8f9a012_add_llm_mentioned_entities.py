"""add llm_mentioned_entities table (Phase 5.5)

Revision ID: c6d7e8f9a012
Revises: b5c6d7e8f901
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c6d7e8f9a012"
down_revision: Union[str, Sequence[str], None] = "b5c6d7e8f901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_mentioned_entities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_log_id", sa.String(), nullable=False),
        sa.Column("mentioned_name", sa.String(length=300), nullable=False),
        sa.Column("context_snippet", sa.String(length=500), nullable=True),
        sa.Column(
            "detected_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="unreviewed"),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("dismissal_reason", sa.String(), nullable=True),
        sa.Column("promoted_to_contribution_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["chat_log_id"], ["chat_logs.id"]),
        sa.ForeignKeyConstraint(["promoted_to_contribution_id"], ["contributions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_log_id", "mentioned_name", name="uq_llm_mention_chat_name"),
    )
    op.create_index("ix_llm_mentions_detected_at", "llm_mentioned_entities", ["detected_at"], unique=False)
    op.create_index("ix_llm_mentions_status", "llm_mentioned_entities", ["status"], unique=False)
    op.create_index("ix_llm_mentions_chat_log_id", "llm_mentioned_entities", ["chat_log_id"], unique=False)
    op.create_index("ix_llm_mentions_mentioned_name", "llm_mentioned_entities", ["mentioned_name"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_llm_mentions_mentioned_name", table_name="llm_mentioned_entities")
    op.drop_index("ix_llm_mentions_chat_log_id", table_name="llm_mentioned_entities")
    op.drop_index("ix_llm_mentions_status", table_name="llm_mentioned_entities")
    op.drop_index("ix_llm_mentions_detected_at", table_name="llm_mentioned_entities")
    op.drop_table("llm_mentioned_entities")
