"""Event window queries with RRULE expansion (Phase 9a)."""

from __future__ import annotations

from datetime import date, time, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.models import Category, Entity, EntityCategory, Event, Provider
from app.events.recurrence import occurrences_in_window
from app.providers import queries as provider_queries

if TYPE_CHECKING:
    from app.providers.view_models import HavaCardViewModel


def event_window_for_chip(when: str, *, today: date) -> tuple[date, date]:
    """Map category-page ``?when=`` chip values to inclusive date windows."""
    key = (when or "").strip().lower()
    if key == "today":
        return today, today
    if key == "this-week":
        days_to_sunday = (6 - today.weekday()) % 7
        return today, today + timedelta(days=days_to_sunday)
    if key == "this-weekend":
        if today.weekday() < 4:
            days_to_friday = (4 - today.weekday()) % 7
            friday = today + timedelta(days=days_to_friday)
        else:
            friday = today
        days_to_sunday = (6 - friday.weekday()) % 7
        return friday, friday + timedelta(days=days_to_sunday)
    if key == "next-month":
        if today.month == 12:
            start = date(today.year + 1, 1, 1)
            end = date(today.year + 1, 1, 31)
        else:
            start = date(today.year, today.month + 1, 1)
            if today.month + 1 == 12:
                end = date(today.year, 12, 31)
            else:
                end = date(today.year, today.month + 2, 1) - timedelta(days=1)
        return start, end
    return today, today + timedelta(days=30)


def intent_window_for_when(when: str, *, today: date) -> tuple[date, date]:
    """Chat event-intent windows (tonight maps to today)."""
    key = (when or "").strip().lower()
    if key == "tonight":
        return today, today
    if key == "this_weekend":
        return event_window_for_chip("this-weekend", today=today)
    if key == "today":
        return today, today
    if key == "tomorrow":
        tomorrow = today + timedelta(days=1)
        return tomorrow, tomorrow
    return today, today + timedelta(days=7)


def events_in_window(
    db: Session,
    *,
    window_start: date,
    window_end: date,
    category_slug: str | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
    limit: int = 50,
) -> list[tuple[Event, date]]:
    """Return (event, occurrence_date) tuples sorted chronologically."""
    stmt = (
        select(Event)
        .where(Event.status == "live")
        .where(
            or_(
                and_(
                    Event.is_recurring.is_(False),
                    Event.date.between(window_start, window_end),
                ),
                Event.is_recurring.is_(True),
                Event.rrule.isnot(None),
                Event.rdate.isnot(None),
            )
        )
    )
    if category_slug:
        stmt = (
            stmt.join(Entity, Entity.id == Event.entity_id)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .join(Category, Category.id == EntityCategory.category_id)
            .where(Category.slug == category_slug)
        )

    candidates = list(db.scalars(stmt).unique().all())
    flat = occurrences_in_window(
        candidates, window_start=window_start, window_end=window_end
    )
    start_bound = _parse_hhmm_bound(time_start)
    end_bound = _parse_hhmm_bound(time_end)
    seen: set[tuple[str, date]] = set()
    filtered: list[tuple[Event, date]] = []
    for ev, occ_date in flat:
        key = (str(ev.id), occ_date)
        if key in seen:
            continue
        seen.add(key)
        if not _event_start_in_time_window(ev.start_time, start_bound, end_bound):
            continue
        filtered.append((ev, occ_date))
    return filtered[:limit]


def _parse_hhmm_bound(value: str | None) -> tuple[int, int] | None:
    if not value or not str(value).strip():
        return None
    parts = str(value).strip().split(":")
    if len(parts) < 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def _event_start_in_time_window(
    start_time: time | None,
    start_bound: tuple[int, int] | None,
    end_bound: tuple[int, int] | None,
) -> bool:
    """True when no time bounds are set, or ``start_time`` falls in [start, end]."""
    if start_bound is None and end_bound is None:
        return True
    if start_time is None:
        return False
    minutes = start_time.hour * 60 + start_time.minute
    if start_bound is not None:
        start_min = start_bound[0] * 60 + start_bound[1]
        if minutes < start_min:
            return False
    if end_bound is not None:
        end_min = end_bound[0] * 60 + end_bound[1]
        if minutes > end_min:
            return False
    return True


def venue_events_for_profile(
    db: Session,
    provider: Provider,
    *,
    limit: int = 5,
    today: date | None = None,
) -> list[HavaCardViewModel]:
    """Upcoming event cards for a provider profile (deduped per logical event)."""

    today = today or date.today()
    horizon_end = today + timedelta(days=60)
    venue_entity_id = provider.entity_id

    candidates = list(
        db.scalars(
            select(Event)
            .where(Event.status == "live")
            .where(
                or_(
                    Event.entity_id == venue_entity_id,
                    Event.provider_id == provider.id,
                )
            )
            .where(
                or_(
                    and_(
                        Event.is_recurring.is_(False),
                        Event.date.between(today, horizon_end),
                    ),
                    Event.is_recurring.is_(True),
                    Event.rrule.isnot(None),
                    Event.rdate.isnot(None),
                )
            )
        ).all()
    )

    flat = occurrences_in_window(
        candidates, window_start=today, window_end=horizon_end
    )
    seen: set[str] = set()
    cards: list[HavaCardViewModel] = []
    for event, occ_date in flat:
        if event.id in seen:
            continue
        seen.add(event.id)
        vm = provider_queries.build_card_view_model_for_event_occurrence(
            db, event.id, occ_date
        )
        if vm is not None:
            cards.append(vm)
        if len(cards) >= limit:
            break
    return cards
