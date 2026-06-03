"""Screenshot capture bridge — additive ``scrape_captures`` image-inbox table.

Revision ID: e2f3a4b5c6d7
Revises: c7e8f9a0b1c2
Create Date: 2026-06-03

OpenClaw uploads Facebook-post screenshots (or metadata-only ``flagged`` rows)
here; a Cowork skill reads/judges the queue later. Additive + nullable-friendly:
only ``source_url`` and ``status`` are required. ``created_at`` uses a
``sa.func.now()`` server default (photos-table precedent).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "c7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scrape_captures",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("business_name", sa.String(), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=True),
        sa.Column("image_url", sa.String(length=2048), nullable=True),
        sa.Column("image_key", sa.String(length=512), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="new",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('new', 'reviewed', 'discarded', 'flagged')",
            name="ck_scrape_captures_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scrape_captures_status", "scrape_captures", ["status"], unique=False
    )
    op.create_index(
        "ix_scrape_captures_created_at", "scrape_captures", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_scrape_captures_created_at", table_name="scrape_captures")
    op.drop_index("ix_scrape_captures_status", table_name="scrape_captures")
    op.drop_table("scrape_captures")
