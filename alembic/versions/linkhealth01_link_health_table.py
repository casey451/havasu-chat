"""Link-health monitoring table.

Adds ``link_health`` — one row per stored outbound URL, tracking its resolve
status across sweeps so a dead link can be confirmed over multiple runs and
surfaced for review. Purely structural + additive; the VPS sweep
(``app.monitoring.link_health``) populates it. Nothing user-facing reads it.

Revision ID: linkhealth01
Revises: p6analyticsidx01
Create Date: 2026-06-25
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "linkhealth01"
down_revision: Union[str, Sequence[str], None] = "p6analyticsidx01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "link_health",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=True),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("detail", sa.String(length=512), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_checked_at", sa.DateTime(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(), nullable=False),
        sa.Column("last_ok_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_broken", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_link_health_url", "link_health", ["url"], unique=True)
    op.create_index("ix_link_health_confirmed_broken", "link_health", ["confirmed_broken"])


def downgrade() -> None:
    op.drop_index("ix_link_health_confirmed_broken", table_name="link_health")
    op.drop_index("ix_link_health_url", table_name="link_health")
    op.drop_table("link_health")
