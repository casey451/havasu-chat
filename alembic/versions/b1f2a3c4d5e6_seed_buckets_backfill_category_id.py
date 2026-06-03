"""seed missing Category buckets + backfill Provider.category_id

Seeds the tier-1 Category buckets the routes expose but the table lacked
(things-to-do, professional, beauty-care, attractions, services), then assigns
category_id to providers where it's NULL, per app.categories.backfill_plan.
Only NULL rows are touched; existing assignments are preserved. Reversible.

Revision ID: b1f2a3c4d5e6
Revises: a3d1g2e3s4t5
"""

from __future__ import annotations

from alembic import op

from app.categories.backfill_plan import reverse_backfill, seed_and_backfill

revision = "b1f2a3c4d5e6"
down_revision = "a3d1g2e3s4t5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    seed_and_backfill(op.get_bind())


def downgrade() -> None:
    reverse_backfill(op.get_bind())
