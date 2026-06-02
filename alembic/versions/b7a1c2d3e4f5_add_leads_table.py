"""Phase B7: leads table (pay-per-lead plumbing, DORMANT).

Adds the ``leads`` table backing the flag-gated lead-capture scaffolding (see
:class:`app.db.models.Lead`). Purely additive and reversible. The capture path
is dormant behind the ``LEADS_ENABLED`` env flag (default OFF); this migration
only creates the storage. NO billing/payment/pricing schema lives here.

Revision ID: b7a1c2d3e4f5
Revises: a3d1g2e3s4t5
Create Date: 2026-06-02
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b7a1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "a3d1g2e3s4t5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("provider_id", sa.String(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="web_form",
        ),
        sa.Column("intent_key", sa.String(length=64), nullable=True),
        sa.Column("chat_log_id", sa.String(), nullable=True),
        sa.Column("query_log_id", sa.String(), nullable=True),
        sa.Column("contact_name", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=64), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chat_log_id"], ["chat_logs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["query_log_id"], ["query_log.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_leads_provider_id", "leads", ["provider_id"])
    op.create_index("ix_leads_category", "leads", ["category"])
    op.create_index("ix_leads_status", "leads", ["status"])
    op.create_index("ix_leads_created_at", "leads", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_leads_created_at", table_name="leads")
    op.drop_index("ix_leads_status", table_name="leads")
    op.drop_index("ix_leads_category", table_name="leads")
    op.drop_index("ix_leads_provider_id", table_name="leads")
    op.drop_table("leads")
