"""create feedback table

DB-backed feedback channel (P5, §2.4). Every "report wrong or missing info" /
footer feedback submission writes a row here (source of truth, admin-visible)
before a Resend notification fires. Anonymized: only an optional reply email is
stored; no IP / user-agent / user-id column exists.

``created_at`` uses ``sa.func.now()`` as a server default so a row inserted via
raw SQL still timestamps, matching the ``contributions`` table's convention.

Revision ID: p5feedback01
Revises: bae799ca267d
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p5feedback01"
down_revision = "bae799ca267d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_ref", sa.String(length=255), nullable=True),
        sa.Column("page_url", sa.String(length=2048), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_status", "feedback", ["status"], unique=False)
    op.create_index(
        "ix_feedback_created_at", "feedback", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_created_at", table_name="feedback")
    op.drop_index("ix_feedback_status", table_name="feedback")
    op.drop_table("feedback")
