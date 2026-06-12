"""relabel category names: Health & Medical, Fitness Sports & Classes

Revision ID: 8d2b58f94e90
Revises: a2c4e6f8b0d2
Create Date: 2026-06-12 11:37:08.313393

Data-only relabel of two ``categories.name`` rows so the directory pages
(/categories/{slug} render their H1 / breadcrumb / JSON-LD from the DB
``Category.name``) agree with the CATEGORY_LABELS dict already relabeled in
PR #296 for Home/Map/Chat. No schema change. ``auto-rv-fuel`` already reads
``Auto, RV & Fuel`` in the DB and is intentionally left untouched.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '8d2b58f94e90'
down_revision: Union[str, Sequence[str], None] = 'a2c4e6f8b0d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Relabel to match CATEGORY_LABELS."""
    op.execute("UPDATE categories SET name = 'Health & Medical' WHERE slug = 'health-wellness-care'")
    op.execute("UPDATE categories SET name = 'Fitness, Sports & Classes' WHERE slug = 'classes-sports-recreation'")


def downgrade() -> None:
    """Restore the prior category names."""
    op.execute("UPDATE categories SET name = 'Health, Wellness & Care' WHERE slug = 'health-wellness-care'")
    op.execute("UPDATE categories SET name = 'Classes, Sports & Recreation' WHERE slug = 'classes-sports-recreation'")
