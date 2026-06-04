"""seed the 13th canonical Category ``professional-services`` + repoint category_id

WP-9 step 2: the code taxonomy gained ``professional-services`` but the DB only
had the older ``professional`` bucket. Seeds the canonical row (idempotent) and
repoints ``Provider.category_id`` for providers whose
``primary_category='professional-services'`` and whose category_id is NULL or
points at the legacy ``professional`` bucket. Reversible.

Revision ID: e5f6a7b8c9d1
Revises: c3d4e5f6a7b8
"""

from __future__ import annotations

from alembic import op

from app.categories.backfill_plan import (
    reverse_professional_services,
    seed_professional_services,
)

revision = "e5f6a7b8c9d1"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    seed_professional_services(op.get_bind())


def downgrade() -> None:
    reverse_professional_services(op.get_bind())
