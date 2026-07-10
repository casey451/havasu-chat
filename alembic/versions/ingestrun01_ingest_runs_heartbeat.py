"""WS12 — ingest_runs per-connector scrape heartbeat.

Revision ID: ingestrun01
Revises: srcparity01
Create Date: 2026-07-09

One additive table. A row is written per scrape-source run (regardless of dedup
outcome) so the freshness canary can distinguish "ran, found nothing" from
"silently broke". No changes to existing tables.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "ingestrun01"
down_revision: Union[str, Sequence[str], None] = "srcparity01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("ran_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ok"),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payloads_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingest_runs_source", "ingest_runs", ["source"])
    op.create_index("ix_ingest_runs_ran_at", "ingest_runs", ["ran_at"])


def downgrade() -> None:
    op.drop_index("ix_ingest_runs_ran_at", table_name="ingest_runs")
    op.drop_index("ix_ingest_runs_source", table_name="ingest_runs")
    op.drop_table("ingest_runs")
