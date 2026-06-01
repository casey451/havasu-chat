"""Snowbird-return reopened-entity query (Phase 7)."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.timezone import LAKE_HAVASU_TZ, now_lake_havasu
from app.db.models import Entity
from app.providers.queries import _active_season_key_for_date, effective_seasonal_hours

SNOWBIRD_PANEL_LIMIT = 20

# Lake Havasu snowbird window (operator lock 2026-05-20).
SNOWBIRD_SEASON_START = (10, 1)  # Oct 1
SNOWBIRD_SEASON_END = (4, 30)  # Apr 30


def is_snowbird_calendar_window(d: date) -> bool:
    """True when ``d`` falls in Oct 1 – Apr 30 (inclusive)."""
    if d.month >= SNOWBIRD_SEASON_START[0]:
        return True
    if d.month < SNOWBIRD_SEASON_END[0]:
        return True
    if d.month == SNOWBIRD_SEASON_END[0]:
        return d.day <= SNOWBIRD_SEASON_END[1]
    return False


def user_has_snowbird_activity_pattern(
    last_active_at: datetime | None,
    *,
    now: datetime | None = None,
) -> bool:
    """Snowbird panel eligibility from ``last_active_at`` (operator lock)."""
    if last_active_at is None:
        return False
    now_dt = now or now_lake_havasu()
    if last_active_at.tzinfo is None:
        last_active_at = last_active_at.replace(tzinfo=LAKE_HAVASU_TZ)
    if (now_dt - last_active_at).days <= 90:
        return True
    la_date = last_active_at.date()
    if is_snowbird_calendar_window(la_date):
        return True
    return False


def _prior_month(d: date) -> date:
    if d.month == 1:
        return date(d.year - 1, 12, 1)
    return date(d.year, d.month - 1, 1)


def _entity_season_open(ent: Entity, d: date) -> bool:
    if ent.seasonal_hours is None or not isinstance(ent.seasonal_hours, dict):
        return False
    key = _active_season_key_for_date(d)
    block = ent.seasonal_hours.get(key)
    if block is None:
        return False
    season, hours, _copy = effective_seasonal_hours(
        ent, now=datetime(d.year, d.month, 15, 12, 0, tzinfo=LAKE_HAVASU_TZ)
    )
    return season is not None and hours is not None


def entity_reopened_after_seasonal_gap(ent: Entity, *, now: date | None = None) -> bool:
    """True when open this season but the prior calendar month was in a closed season."""
    ref = now or now_lake_havasu().date()
    if not _entity_season_open(ent, ref):
        return False
    prior = _prior_month(ref)
    # Mid-prior-month sample date.
    _, last_day = monthrange(prior.year, prior.month)
    sample_prior = date(prior.year, prior.month, min(15, last_day))
    return not _entity_season_open(ent, sample_prior)


def get_snowbird_reopened_entities(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = SNOWBIRD_PANEL_LIMIT,
) -> list[Entity]:
    """Entities whose seasonal_hours indicate a reopen after the prior month was closed."""
    now_dt = now or now_lake_havasu()
    ref_date = now_dt.date()
    rows = list(
        db.scalars(
            select(Entity)
            .where(
                Entity.is_active.is_(True),
                Entity.seasonal_hours.isnot(None),
            )
            .options(joinedload(Entity.location))
            .limit(500)
        )
        .unique()
        .all()
    )
    reopened = [e for e in rows if entity_reopened_after_seasonal_gap(e, now=ref_date)]
    reopened.sort(key=lambda e: (e.name or "").lower())
    return reopened[:limit]


__all__ = [
    "SNOWBIRD_PANEL_LIMIT",
    "entity_reopened_after_seasonal_gap",
    "get_snowbird_reopened_entities",
    "is_snowbird_calendar_window",
    "user_has_snowbird_activity_pattern",
]
