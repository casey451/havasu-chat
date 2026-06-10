"""Create admin_audit_log (admin portal audit trail — Track E wiring).

Promoted from ``app/admin_portal/migrations_draft/0001_create_admin_audit_log.py``
per its docstring. New-table-only — no existing data touched. The portal
degrades gracefully when the table is absent (audit writes skip, the audit
page shows a setup notice), so downgrade is safe too.

Chains after c7e3a9d1f5b8 (the Track A café-slug data fix) — this PR stacks
on fix/security-ops-batch, which must merge first.

Revision ID: e9b5d7f3a1c6
Revises: c7e3a9d1f5b8
Create Date: 2026-06-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e9b5d7f3a1c6"
down_revision: str | Sequence[str] | None = "c7e3a9d1f5b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False, server_default="admin"),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
    )
    op.create_index("ix_admin_audit_log_created_at", "admin_audit_log", ["created_at"])
    op.create_index("ix_admin_audit_log_target", "admin_audit_log", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_index("ix_admin_audit_log_target", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_created_at", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
