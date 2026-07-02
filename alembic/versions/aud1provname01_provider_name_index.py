"""providers.provider_name index (audit 2026-07-01).

Exact-match lookups on the chat path (app/core/session.py record_entity),
admin/API ilike searches, and the slug-allocation prefix probes all filter on
``provider_name``; the column had no index. Plain additive index — safe to run
on prod via the preDeploy ``alembic upgrade head``.

Revision ID: aud1provname01
Revises: linkassess02
"""

from __future__ import annotations

from alembic import op

revision = "aud1provname01"
down_revision = "linkassess02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_providers_provider_name", "providers", ["provider_name"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_providers_provider_name", table_name="providers")
