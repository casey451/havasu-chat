"""Admin Jobs portal — additive ``jobs`` work-queue table.

Revision ID: b9c0d1e2f3a4
Revises: 24b922964acd
Create Date: 2026-06-03

One row per admin-queued scraper-pipeline job. Worker agents (Cowork / OpenClaw)
poll, atomically claim, and PATCH these rows. Additive + standalone (no FKs);
only ``id``, ``job_type``, ``status`` are required. ``created_at`` uses a
``sa.func.now()`` server default (scrape_captures / photos precedent).

Chains linearly after the liveness migration ``24b922964acd`` (merged to main in
PR #104), keeping a single alembic head — no merge revision needed.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, Sequence[str], None] = "24b922964acd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("requested_by", sa.String(), nullable=True),
        sa.Column("claimed_by", sa.String(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "job_type IN ('schedule_hunt', 'fb_capture_sweep', 'capture_review', "
            "'publish_approved', 'discovery_audit')",
            name="ck_jobs_job_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'claimed', 'running', 'done', 'failed')",
            name="ck_jobs_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"], unique=False)
    op.create_index("ix_jobs_job_type", "jobs", ["job_type"], unique=False)
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_jobs_created_at", table_name="jobs")
    op.drop_index("ix_jobs_job_type", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_table("jobs")
