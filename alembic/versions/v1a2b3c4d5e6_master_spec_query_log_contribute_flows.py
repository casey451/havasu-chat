"""Master spec v1: query_log + contribute_flows tables.

Revision ID: v1a2b3c4d5e6
Revises: d3e4f5a6b7c8
Create Date: 2026-05-31
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "v1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "query_log",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("normalized_intent", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_query_log_normalized_intent", "query_log", ["normalized_intent"])
    op.create_index("ix_query_log_category", "query_log", ["category"])
    op.create_index("ix_query_log_created_at", "query_log", ["created_at"])

    op.create_table(
        "contribute_flows",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("contribution_type", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=2048), nullable=True),
        sa.Column("extraction", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contribute_flows_session_id", "contribute_flows", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_contribute_flows_session_id", table_name="contribute_flows")
    op.drop_table("contribute_flows")
    op.drop_index("ix_query_log_created_at", table_name="query_log")
    op.drop_index("ix_query_log_category", table_name="query_log")
    op.drop_index("ix_query_log_normalized_intent", table_name="query_log")
    op.drop_table("query_log")
