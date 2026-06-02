"""Weekend digest builder (Phase A3).

Builds a per-user "This weekend in Havasu" digest:

  * ``weekend_events`` — everything happening this weekend (Fri-Sun) city-wide,
    via :func:`app.events.queries.events_in_window` over the canonical
    "this-weekend" window from :func:`event_window_for_chip`.
  * ``saved_venue_events`` — the subset happening at the user's saved/followed
    venues (see :mod:`app.digest.saved_venue`).

Honesty rules (no fabrication):
  * Empty windows yield empty lists, never placeholder/sample events.
  * ``has_content`` is False when both lists are empty so callers / templates
    can render an honest "nothing on the calendar yet" empty state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.db.models import Event
from app.digest.saved_venue import saved_venue_events_for_user
from app.events.queries import event_window_for_chip, events_in_window

# Cap how many events we surface per section so a dry-run render stays bounded.
_WEEKEND_LIMIT = 25
_SAVED_VENUE_LIMIT = 25


@dataclass(frozen=True)
class DigestEvent:
    """A single occurrence flattened for rendering. No invented fields."""

    event_id: str
    title: str
    occurrence_date: date
    location_name: str
    event_url: str

    @classmethod
    def from_occurrence(cls, event: Event, occ_date: date) -> "DigestEvent":
        return cls(
            event_id=str(event.id),
            title=event.title,
            occurrence_date=occ_date,
            location_name=event.location_name or "",
            event_url=event.event_url or "",
        )


@dataclass(frozen=True)
class WeekendDigest:
    """Per-user weekend digest payload (data only; rendering is separate)."""

    user_id: str
    window_start: date
    window_end: date
    weekend_events: list[DigestEvent] = field(default_factory=list)
    saved_venue_events: list[DigestEvent] = field(default_factory=list)

    @property
    def has_content(self) -> bool:
        return bool(self.weekend_events or self.saved_venue_events)

    @property
    def has_saved_venue_events(self) -> bool:
        return bool(self.saved_venue_events)


def build_weekend_digest(
    db: Session,
    user_id: str,
    *,
    today: date | None = None,
) -> WeekendDigest:
    """Build (do not send) the weekend digest for ``user_id``.

    ``today`` is injectable for deterministic tests; defaults to ``date.today()``.
    """
    today = today or date.today()
    window_start, window_end = event_window_for_chip("this-weekend", today=today)

    weekend_pairs = events_in_window(
        db,
        window_start=window_start,
        window_end=window_end,
        limit=_WEEKEND_LIMIT,
    )
    saved_pairs = saved_venue_events_for_user(
        db,
        user_id,
        window_start=window_start,
        window_end=window_end,
        limit=_SAVED_VENUE_LIMIT,
    )

    return WeekendDigest(
        user_id=user_id,
        window_start=window_start,
        window_end=window_end,
        weekend_events=[DigestEvent.from_occurrence(e, d) for e, d in weekend_pairs],
        saved_venue_events=[DigestEvent.from_occurrence(e, d) for e, d in saved_pairs],
    )
