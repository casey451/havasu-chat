"""Expand venue class Schedules into calendar occurrences (read-time bridge).

The captured gym/class schedules live as recurring ``Schedule`` rows on venue
Entities (published by ``scripts/import_captured_schedules.py``) -- NOT as
``Event`` rows. They render on ``/provider/<slug>`` pages, but the home month
calendar and ``/events-ui`` read the events table only, so a "Mon-Thu BJJ"
venue looked empty on the calendar. This module is the read-time bridge: it
expands recurring Schedule rows into dated occurrences so the calendar views
can union them in, without double-writing class data into the events table.

Dedup contract: some venues' classes exist BOTH as events (the parks-rec
aquatic programs are ingested as recurring Events) and as captured Schedule
rows. Callers pass the (lowercased title, date) keys of the event occurrences
they already have; matching class occurrences are dropped so "Lap Swim" never
shows twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta

from sqlalchemy.orm import Session

from app.db.models import Entity, Provider, Schedule

_DAY_TO_INT = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

# Safety valve: the calendar asks for at most a month; never expand more.
_MAX_WINDOW_DAYS = 62


@dataclass(frozen=True)
class ClassOccurrence:
    title: str
    date: date
    start_time: time | None
    end_time: time | None
    venue: str
    provider_slug: str | None
    weekdays: frozenset[int]  # Mon=0 .. Sun=6 -- the series' full pattern

    @property
    def url(self) -> str:
        """Class series have no event permalink; link to the venue's page."""
        if self.provider_slug:
            return f"/provider/{self.provider_slug}"
        return "/events-ui"


def class_occurrences_in_window(
    db: Session, *, window_start: date, window_end: date
) -> list[ClassOccurrence]:
    """All recurring-Schedule class occurrences in the inclusive date window."""
    if window_end < window_start:
        return []
    window_end = min(window_end, window_start + timedelta(days=_MAX_WINDOW_DAYS))

    rows = (
        db.query(Schedule, Entity, Provider)
        .join(Entity, Schedule.entity_id == Entity.id)
        .outerjoin(Provider, Provider.entity_id == Entity.id)
        .filter(
            Schedule.schedule_type == "recurring",
            Schedule.days_of_week.isnot(None),
            Entity.is_active.is_(True),
        )
        .all()
    )

    out: list[ClassOccurrence] = []
    for sched, ent, prov in rows:
        title = (sched.notes or "").strip()
        if not title:
            continue  # untitled rows are junk on the venue page too
        weekdays = frozenset(
            _DAY_TO_INT[d.lower()]
            for d in (sched.days_of_week or [])
            if isinstance(d, str) and d.lower() in _DAY_TO_INT
        )
        if not weekdays:
            continue
        if prov is not None and prov.is_active is False:
            prov = None
        venue = (ent.name or "").strip()
        slug = prov.slug if prov is not None else None
        d = window_start
        while d <= window_end:
            if d.weekday() in weekdays:
                out.append(
                    ClassOccurrence(
                        title=title,
                        date=d,
                        start_time=sched.start_time,
                        end_time=sched.end_time,
                        venue=venue,
                        provider_slug=slug,
                        weekdays=weekdays,
                    )
                )
            d += timedelta(days=1)
    out.sort(key=lambda o: (o.date, o.start_time or time(0, 0), o.venue, o.title))
    return out


def drop_event_duplicates(
    occurrences: list[ClassOccurrence], event_keys: set[tuple[str, date]]
) -> list[ClassOccurrence]:
    """Drop class occurrences already represented by a live Event occurrence
    (same lowercased title on the same date) -- e.g. the aquatic programs."""
    return [
        o for o in occurrences if (o.title.strip().lower(), o.date) not in event_keys
    ]
