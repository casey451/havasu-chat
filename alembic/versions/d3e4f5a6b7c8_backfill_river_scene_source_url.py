"""Backfill Event.source_url for river_scene imports (chain-heal reconstruction).

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-05-31

Background
----------
This revision was originally authored on an unmerged branch (the river_scene
consolidation, "Task B" / PR #63) and a local SQLite database was stamped at
``d3e4f5a6b7c8`` after it was applied by hand. The version file itself never
landed on ``main``, so any database stamped at this revision could no longer
``alembic upgrade head`` -- alembic raised "Can't locate revision identified by
'd3e4f5a6b7c8'". See ``DEPLOY_MIGRATION_GAP.md``.

It is reconstructed here, faithfully, from the original spec (recorded in
``SESSION_HANDOFF_2026-05-30_golakehavasu-followups-DONE.md``) and re-inserted
into the chain between ``c2d3e4f5a6b7`` and ``v1a2b3c4d5e6`` so that:
  * a fresh database upgrades straight through it (the backfill is a no-op on an
    empty ``events`` table), and
  * a database already stamped at ``d3e4f5a6b7c8`` can move forward to head with
    no manual stamping.

What it does
------------
Backfills ``events.source_url`` for river_scene imports that predate the
source_url column being populated: sets it to the normalized event URL
(``rtrim(lower(trim(event_url)), '/')``) wherever it is currently NULL. This
mirrors the submission-URL normalization and the legacy dedup WHERE clause.

Idempotent (only touches rows where ``source_url IS NULL``); safe to re-run.
Downgrade is a documented no-op -- the original backfill is irreversible
(the prior NULLs are not recoverable, and there is no harm in leaving the
normalized URLs in place).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Dialect-portable: rtrim(x, '/'), lower(), trim() behave identically on
    # SQLite and PostgreSQL. Only rows missing source_url are touched.
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
    # No-op: the backfill is irreversible (original NULLs are not recoverable).
    pass
