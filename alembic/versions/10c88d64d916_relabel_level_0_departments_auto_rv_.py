"""relabel level-0 departments: Auto RV & Fuel, Fitness Sports & Classes

Revision ID: 10c88d64d916
Revises: 8d2b58f94e90
Create Date: 2026-06-12 12:23:56.161979

Data-only relabel of the two *rendered* level-0 department rows so the home
category nav and ``/categories/{dept}`` pages (both render the level-0
``Category.name`` via ``all_departments`` / ``resolve_department``) read the
agreed labels:

  auto-rv-and-marine  'Auto, RV & Marine'  -> 'Auto, RV & Fuel'
  fitness-and-wellness 'Fitness & Wellness' -> 'Fitness, Sports & Classes'

``Health & Medical`` (slug ``health-and-medical``) is already correct and is
untouched. This is the correction to PR #300, which relabeled the *tier-1*
``categories.name`` rows by slug (``health-wellness-care`` /
``classes-sports-recreation``) — those happen to be level-0 but are childless
legacy rows that render nowhere, so #300 had no visible effect and is left as-is.

Matched by ``slug`` (unique), not by name: childless legacy level-0 rows already
carry the new names (``auto-rv-fuel`` = 'Auto, RV & Fuel';
``classes-sports-recreation`` = 'Fitness, Sports & Classes'), so a name-matched
downgrade would clobber them. Slug-matching keeps both directions precise and
reversible. No schema change. Slugs unchanged (re-slug deferred to the B3 rebuild).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '10c88d64d916'
down_revision: Union[str, Sequence[str], None] = '8d2b58f94e90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Relabel the two rendered level-0 departments."""
    op.execute("UPDATE categories SET name = 'Auto, RV & Fuel' WHERE slug = 'auto-rv-and-marine'")
    op.execute("UPDATE categories SET name = 'Fitness, Sports & Classes' WHERE slug = 'fitness-and-wellness'")


def downgrade() -> None:
    """Restore the prior department names."""
    op.execute("UPDATE categories SET name = 'Auto, RV & Marine' WHERE slug = 'auto-rv-and-marine'")
    op.execute("UPDATE categories SET name = 'Fitness & Wellness' WHERE slug = 'fitness-and-wellness'")
