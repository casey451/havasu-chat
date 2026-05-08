"""merge cache_v2 with home_page (no-op fan-in)

Two parallel migration chains both descend from ``c1a2b3c4d5e6``:

  - home-page-design: ``d2e3f4a5b6c7`` (featured cols) →
                      ``e3f4a5b6c7d8`` (sponsors table)
  - cache-v2 (§4.3):  ``f5b6c7d8e9a0`` (llm_response_cache.query_embedding)

Alembic refuses to ``upgrade head`` while two heads exist; this revision
declares both as parents so the graph collapses back to a single tip.
``upgrade()`` and ``downgrade()`` are no-ops — the actual schema work lives
on the parent revisions.

When you ship, run ``alembic upgrade head`` and Alembic will apply the
parents in any safe order, then mark this revision as the current head.

Revision ID: 1a2b3c4d5e6f
Revises: e3f4a5b6c7d8, f5b6c7d8e9a0
Create Date: 2026-05-08

NB: keep this file alongside the two parent migrations on whichever branch
ships last. If the home-page-design branch is squashed/rebased before merge
and the parent revision IDs change, edit the ``down_revision`` tuple below
to match the new IDs.
"""

from typing import Sequence, Union

revision: str = "1a2b3c4d5e6f"
down_revision: Union[str, Sequence[str], None] = ("e3f4a5b6c7d8", "f5b6c7d8e9a0")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op merge — schema changes live on the parent revisions."""


def downgrade() -> None:
    """No-op merge — schema rollback lives on the parent revisions."""
