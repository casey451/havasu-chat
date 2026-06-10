"""Rename the broken café taxonomy leaf slug (B1, 2026-06-10).

The A.3 taxonomy seed generated ``caf-s-and-coffee`` for the "Cafés & Coffee"
leaf — the slugifier dropped the non-ASCII ``é`` and left the stray hyphen.
One-row data fix: rename to ``cafes-and-coffee``. Code references update in
the same deploy (``app/categories/leaf_seo.py`` / ``leaf_query.py``), the old
URL 301s permanently via ``LEAF_SLUG_ALIASES`` in ``app/categories/router.py``,
and ``app.utils.slug.slugify`` is now unicode-aware so the bug can't recur.

No-op on databases without the seeded taxonomy (matches 0 rows — local dev /
CI SQLite included).

Revision ID: c7e3a9d1f5b8
Revises: b2d4f6a8c0e2
Create Date: 2026-06-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "c7e3a9d1f5b8"
down_revision: str | Sequence[str] | None = "b2d4f6a8c0e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE categories SET slug = 'cafes-and-coffee' "
        "WHERE slug = 'caf-s-and-coffee' AND level = 1"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE categories SET slug = 'caf-s-and-coffee' "
        "WHERE slug = 'cafes-and-coffee' AND level = 1"
    )
