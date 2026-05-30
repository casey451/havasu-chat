"""backfill river_scene_import event source_url from event_url

Prerequisite for Task B (river_scene dedup consolidation). Pre-Commit-1
river_scene_import Event rows may have ``source_url IS NULL`` while
``event_url`` still holds the original article URL. ``river_scene_pull`` today
protects those rows with a bespoke legacy branch
(``_duplicate_rs_article_import``'s NULL-source_url fallback). Once this
backfill runs, ``event_reconciler.reconcile_event``'s ``source_url`` exact-match
tier subsumes that legacy branch, so the bespoke check can be deleted.

Backfill rule mirrors ``app.db.contribution_store.normalize_submission_url``
(lower + strip + drop trailing slash) so the values match what reconcile_event
computes from incoming payloads.

Idempotent: only touches rows where ``source_url IS NULL`` and
``source = 'river_scene_import'`` with a non-empty ``event_url``. Re-running is a
no-op. Irreversible (cannot know which rows were originally NULL), so downgrade
is a documented no-op.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-05-30 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: str | Sequence[str] | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # lower(trim(...)) + rtrim('/') matches normalize_submission_url and the
    # existing legacy WHERE clause in river_scene_pull (func.lower/func.rtrim).
    # Portable across PostgreSQL (prod) and SQLite (tests).
    op.execute(
        """
        UPDATE events
        SET source_url = rtrim(lower(trim(event_url)), '/')
        WHERE source_url IS NULL
          AND source = 'river_scene_import'
          AND event_url IS NOT NULL
          AND trim(event_url) <> ''
        """
    )


def downgrade() -> None:
    # Irreversible data backfill: the original NULL/non-NULL distribution is not
    # recoverable. Intentional no-op.
    pass
