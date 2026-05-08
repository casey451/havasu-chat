"""add llm_response_cache table for Tier 3 synthesis caching

Stream C of the voice quality + cost containment plan
(see relay/HAVA_VOICE_QUALITY_MASTER_PLAN_2026-05-07.md). Adds a single
table that caches Tier 3 (and optionally Tier 2 LLM) responses keyed by
normalized_query + context_hash + rubric_version. Hits bump a counter
and last_hit_at; misses fall through to the live LLM call which writes
the response back. Expired entries (TTL passed) are treated as misses
and overwritten on the next miss.

Cross-dialect (SQLite + Postgres) DDL via standard ``op.create_table``.

Revision ID: c1a2b3c4d5e6
Revises: e9f0a1b2c3d4
Create Date: 2026-05-08

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_response_cache",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("normalized_query", sa.String(length=500), nullable=False),
        sa.Column("context_hash", sa.String(length=32), nullable=False),
        sa.Column("rubric_version", sa.String(length=32), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("tier_used", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_hit_at", sa.DateTime(), nullable=True),
        sa.Column(
            "hit_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("ttl_until", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_llm_response_cache_cache_key",
        "llm_response_cache",
        ["cache_key"],
        unique=True,
    )
    op.create_index(
        "ix_llm_response_cache_rubric_version",
        "llm_response_cache",
        ["rubric_version"],
        unique=False,
    )
    op.create_index(
        "ix_llm_response_cache_ttl_until",
        "llm_response_cache",
        ["ttl_until"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_llm_response_cache_ttl_until", table_name="llm_response_cache"
    )
    op.drop_index(
        "ix_llm_response_cache_rubric_version", table_name="llm_response_cache"
    )
    op.drop_index(
        "ix_llm_response_cache_cache_key", table_name="llm_response_cache"
    )
    op.drop_table("llm_response_cache")
