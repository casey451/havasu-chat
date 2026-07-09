"""Link-health LLM assessment columns.

Adds the local-LLM verdict + suggested replacement URL (+ check timestamp) for a
confirmed-broken link, surfaced read-only on the admin page. Additive + nullable.

Revision ID: linkassess02
Revises: linkhealth01
Create Date: 2026-06-25
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "linkassess02"
down_revision: Union[str, Sequence[str], None] = "linkhealth01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("link_health", sa.Column("llm_assessment", sa.String(length=512), nullable=True))
    op.add_column("link_health", sa.Column("llm_suggested_url", sa.String(length=2048), nullable=True))
    op.add_column("link_health", sa.Column("llm_checked_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("link_health", "llm_checked_at")
    op.drop_column("link_health", "llm_suggested_url")
    op.drop_column("link_health", "llm_assessment")
