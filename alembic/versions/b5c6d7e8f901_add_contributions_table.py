"""add contributions table (Phase 5.1)

Revision ID: b5c6d7e8f901
Revises: 7a8b9c0d1e2f
Create Date: 2026-04-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5c6d7e8f901"
down_revision: Union[str, Sequence[str], None] = "7a8b9c0d1e2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contributions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("submitter_email", sa.String(), nullable=True),
        sa.Column("submitter_ip_hash", sa.String(length=64), nullable=True),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("submission_name", sa.String(), nullable=False),
        sa.Column("submission_url", sa.String(), nullable=True),
        sa.Column("submission_category_hint", sa.String(), nullable=True),
        sa.Column("submission_notes", sa.Text(), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("event_time_start", sa.Time(), nullable=True),
        sa.Column("event_time_end", sa.Time(), nullable=True),
        sa.Column("url_title", sa.String(), nullable=True),
        sa.Column("url_description", sa.Text(), nullable=True),
        sa.Column("url_fetch_status", sa.String(), nullable=True),
        sa.Column("url_fetched_at", sa.DateTime(), nullable=True),
        sa.Column("google_place_id", sa.String(), nullable=True),
        sa.Column("google_enriched_data", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("rejection_reason", sa.String(), nullable=True),
        sa.Column("created_provider_id", sa.String(), nullable=True),
        sa.Column("created_program_id", sa.String(), nullable=True),
        sa.Column("created_event_id", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="user_submission"),
        sa.Column("llm_source_chat_log_id", sa.String(), nullable=True),
        sa.Column("unverified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["created_event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["created_program_id"], ["programs.id"]),
        sa.ForeignKeyConstraint(["created_provider_id"], ["providers.id"]),
        sa.ForeignKeyConstraint(["llm_source_chat_log_id"], ["chat_logs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contributions_status", "contributions", ["status"], unique=False)
    op.create_index("ix_contributions_source", "contributions", ["source"], unique=False)
    op.create_index("ix_contributions_submitted_at", "contributions", ["submitted_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_contributions_submitted_at", table_name="contributions")
    op.drop_index("ix_contributions_source", table_name="contributions")
    op.drop_index("ix_contributions_status", table_name="contributions")
    op.drop_table("contributions")
