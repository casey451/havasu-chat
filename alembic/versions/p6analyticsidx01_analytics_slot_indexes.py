"""add analytics_events slot / slot_origin composite indexes

P6 perf (audit M1/M2): the admin placement dashboard groups by ``slot`` and the
traffic dashboard groups by coalesce(``slot_origin``, ``slot``), both over a
created_at window. Neither column was indexed, so the group-by was a full scan +
filesort that degrades as ``analytics_events`` grows one row per ad impression
sitewide. Composite ``(col, created_at)`` so the window filter rides the index.

Additive, index-only — no data change, safe to re-run (``IF NOT EXISTS`` via the
create_index ``if_not_exists`` is not portable to SQLite, so we guard on the
inspector instead).

Revision ID: p6analyticsidx01
Revises: p5payint02
Create Date: 2026-06-23
"""

from __future__ import annotations

from sqlalchemy import inspect

from alembic import op

revision = "p6analyticsidx01"
down_revision = "p5payint02"
branch_labels = None
depends_on = None

_TABLE = "analytics_events"
_INDEXES = (
    ("ix_analytics_events_slot_created", ["slot", "created_at"]),
    ("ix_analytics_events_slot_origin_created", ["slot_origin", "created_at"]),
)


def _existing(bind) -> set[str]:
    return {ix["name"] for ix in inspect(bind).get_indexes(_TABLE)}


def upgrade() -> None:
    existing = _existing(op.get_bind())
    for name, cols in _INDEXES:
        if name not in existing:
            op.create_index(name, _TABLE, cols)


def downgrade() -> None:
    existing = _existing(op.get_bind())
    for name, _cols in _INDEXES:
        if name in existing:
            op.drop_index(name, table_name=_TABLE)
