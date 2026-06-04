"""allow 'duplicate' in ck_events_status

The WP-4 cross-source dedupe (scripts/dedupe_events_cross_source.py) marks
collapsed rows ``status='duplicate'`` -- its documented contract since the
audit ("removed from the live feed, keeper carries combined_source"). The
phase-9 CHECK constraint predates that script and rejected the value, so the
apply pass could never run on prod. Add 'duplicate' to the allowed set.

Revision ID: f6a7b8c9d0e2
Revises: e5f6a7b8c9d1
"""

from __future__ import annotations

from alembic import op

revision = "f6a7b8c9d0e2"
down_revision = "e5f6a7b8c9d1"
branch_labels = None
depends_on = None

_OLD = "status IN ('draft', 'live', 'cancelled', 'expired', 'pending_review', 'deleted')"
_NEW = (
    "status IN ('draft', 'live', 'cancelled', 'expired', "
    "'pending_review', 'deleted', 'duplicate')"
)


def upgrade() -> None:
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.drop_constraint("ck_events_status", type_="check")
        batch_op.create_check_constraint("ck_events_status", _NEW)


def downgrade() -> None:
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.drop_constraint("ck_events_status", type_="check")
        batch_op.create_check_constraint("ck_events_status", _OLD)
