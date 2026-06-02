"""Itinerary builder (Lane B5).

Composes a time-ordered, multi-stop day/weekend itinerary from REAL catalog
data only. Each slot is filled by the existing grounded query layer:

  * provider slots (do-something, eat, on-the-water/attraction) ->
    :func:`app.chat.intents.queries.run_query` over a synthetic
    :class:`~app.chat.intents.resolver.ResolvedIntent`, so the picks come from
    exactly the same ranked/honest provider logic the chat uses — no parallel
    query path, no fabricated fields.
  * the evening slot -> :func:`app.events.queries.events_in_window` for the
    requested day, picking the first real event in the evening (else the first
    event of the day), falling back to a nightlife provider when there is no
    event at all.

Honesty rules (no fabrication):
  * A slot with no catalog match is still emitted, but ``filled`` is False, its
    ``pick`` is ``None``, and it carries an honest empty message + a
    ``/contribute`` nudge. We never invent a venue, a time, or an event.
  * Times shown are *suggested* time-of-day windows for the slot, not claimed
    opening hours — except event stops, which use the event's real start time.

Product defaults flagged for Casey (see LANE_SCHEMA.flagged_decisions):
  * Day plan = 4 slots (morning do, lunch eat, afternoon on-the-water, evening
    event). Suggested windows 9am / 12pm / 2pm / 6pm.
  * "this weekend" builds one day plan anchored on the upcoming Saturday.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time

from sqlalchemy.orm import Session

from app.chat.intents.queries import QueryResult, run_query
from app.chat.intents.resolver import ResolvedIntent
from app.core.timezone import now_lake_havasu
from app.events.queries import event_window_for_chip, events_in_window

# Suggested time-of-day anchors for each slot (24h). These are *suggested*
# windows, not claimed business hours.
_MORNING = time(9, 0)
_LUNCH = time(12, 0)
_AFTERNOON = time(14, 0)
_EVENING = time(18, 0)

# An event starting at or after this hour counts as an "evening" event.
_EVENING_CUTOFF_HOUR = 16

_CONTRIBUTE_HREF = "/contribute"
_EVENT_SCAN_LIMIT = 24


@dataclass(frozen=True)
class StopPick:
    """A single concrete catalog item chosen for a slot. No invented fields."""

    kind: str  # "provider" | "event"
    name: str
    href: str | None = None
    detail: str | None = None  # address / location line
    note: str | None = None  # rating, "live event", etc.


@dataclass
class Stop:
    """One time-ordered stop in the itinerary.

    ``filled`` is False when the catalog has nothing for the slot — the stop is
    still shown (honest empty state), but ``pick`` is ``None``.
    """

    slot: str  # "morning" | "lunch" | "afternoon" | "evening"
    label: str  # human heading, e.g. "Morning — something to do"
    suggested_time: time
    pick: StopPick | None = None
    empty_message: str = ""
    contribute_href: str = _CONTRIBUTE_HREF

    @property
    def filled(self) -> bool:
        return self.pick is not None

    @property
    def time_label(self) -> str:
        return _fmt_time(self.suggested_time)

    @property
    def sort_key(self) -> tuple[int, int]:
        return (self.suggested_time.hour, self.suggested_time.minute)


@dataclass
class Itinerary:
    """A time-ordered day itinerary. ``stops`` is always sorted by time."""

    plan_date: date
    title: str
    stops: list[Stop] = field(default_factory=list)

    @property
    def filled_count(self) -> int:
        return sum(1 for s in self.stops if s.filled)

    @property
    def has_any(self) -> bool:
        return self.filled_count > 0

    @property
    def all_empty(self) -> bool:
        return self.filled_count == 0


def _fmt_time(t: time) -> str:
    suffix = "AM" if t.hour < 12 else "PM"
    h12 = t.hour % 12 or 12
    return f"{h12}:{t.minute:02d} {suffix}" if t.minute else f"{h12} {suffix}"


def _first_provider_pick(result: QueryResult) -> StopPick | None:
    """First provider row from a QueryResult as a StopPick, or None if empty."""
    for row in result.rows:
        if row.get("type") != "provider":
            continue
        name = row.get("name")
        if not name:
            continue
        slug = row.get("slug")
        href = f"/provider/{slug}" if slug else None
        rating = row.get("google_rating")
        note = None
        if rating is not None:
            rc = row.get("google_review_count")
            note = f"{rating}★" + (f" ({rc})" if rc else "")
        return StopPick(
            kind="provider",
            name=str(name),
            href=href,
            detail=row.get("address") or None,
            note=note,
        )
    return None


def _provider_stop(
    db: Session,
    *,
    slot: str,
    label: str,
    suggested_time: time,
    intent_key: str,
    slots: dict[str, object],
    today: date,
    empty_message: str,
) -> Stop:
    result = run_query(ResolvedIntent(intent_key, slots), db, today=today)
    return Stop(
        slot=slot,
        label=label,
        suggested_time=suggested_time,
        pick=_first_provider_pick(result),
        empty_message=empty_message,
    )


def _evening_stop(db: Session, *, today: date) -> Stop:
    """Evening slot: prefer a real event today, else a nightlife provider.

    Event picks carry the event's REAL start time (not the suggested window);
    everything is honest — if there is no event and no bar/brewery, the slot is
    an honest empty state.
    """
    pairs = events_in_window(
        db, window_start=today, window_end=today, limit=_EVENT_SCAN_LIMIT
    )
    chosen = None
    chosen_time = _EVENING
    # Prefer the first event starting in the evening; fall back to the earliest
    # event of the day so we never claim an evening time an event doesn't have.
    evening = [(ev, occ) for ev, occ in pairs if _is_evening(ev.start_time)]
    source = evening or pairs
    for ev, _occ in source:
        title = ev.title
        if not title:
            continue
        chosen = StopPick(
            kind="event",
            name=str(title),
            href=ev.event_url or None,
            detail=ev.location_name or None,
            note="Live event",
        )
        if ev.start_time is not None:
            chosen_time = ev.start_time
        break

    if chosen is not None:
        return Stop(
            slot="evening",
            label="Evening — an event",
            suggested_time=chosen_time,
            pick=chosen,
            empty_message="",
        )

    # No event today -> offer a nightlife provider (bars/breweries) instead.
    result = run_query(
        ResolvedIntent("eat_find", {"cuisine": "brewery"}), db, today=today
    )
    pick = _first_provider_pick(result)
    return Stop(
        slot="evening",
        label="Evening — out on the town",
        suggested_time=_EVENING,
        pick=pick,
        empty_message=(
            "No events on the calendar for this day yet, and nothing in the "
            "catalog for a night out. Help us fill it in."
        ),
    )


def _is_evening(t: time | None) -> bool:
    return t is not None and t.hour >= _EVENING_CUTOFF_HOUR


def _resolve_plan_date(when: str | None, today: date) -> tuple[date, str]:
    """Map a free ``when`` token to a concrete day + a human title.

    Supported: "today" (default), "tomorrow", "this_weekend"/"weekend"
    (anchored on the upcoming Saturday). Unknown tokens fall back to today.
    """
    key = (when or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key in ("tomorrow",):
        from datetime import timedelta

        d = today + timedelta(days=1)
        return d, "Your day in Havasu — tomorrow"
    if key in ("this_weekend", "weekend"):
        start, end = event_window_for_chip("this-weekend", today=today)
        from datetime import timedelta

        # Anchor on Saturday when the weekend window includes it, else the start.
        saturday = start + timedelta(days=(5 - start.weekday()) % 7)
        plan_date = saturday if start <= saturday <= end else start
        return plan_date, "Your weekend in Havasu"
    return today, "Your day in Havasu"


def build_itinerary(
    db: Session,
    *,
    when: str | None = None,
    area: str | None = None,
    today: date | None = None,
) -> Itinerary:
    """Build a time-ordered day itinerary from real catalog data only.

    ``when`` accepts "today" (default), "tomorrow", "this_weekend"/"weekend".
    ``area`` optionally biases provider picks toward a district (soft). ``today``
    is injectable for deterministic tests.
    """
    if today is None:
        today = now_lake_havasu().date()
    plan_date, title = _resolve_plan_date(when, today)

    area_slots: dict[str, object] = {"area": area} if area else {}

    stops: list[Stop] = [
        _provider_stop(
            db,
            slot="morning",
            label="Morning — something to do",
            suggested_time=_MORNING,
            intent_key="parks_trails",
            slots=dict(area_slots),
            today=plan_date,
            empty_message=(
                "Nothing in the catalog for a morning outing yet. Know a great "
                "park, trail, or beach? Add it."
            ),
        ),
        _provider_stop(
            db,
            slot="lunch",
            label="Lunch — a bite to eat",
            suggested_time=_LUNCH,
            intent_key="eat_find",
            slots=dict(area_slots),
            today=plan_date,
            empty_message=(
                "No lunch spots in the catalog for this yet. Help us put your "
                "favorite on the map."
            ),
        ),
        _provider_stop(
            db,
            slot="afternoon",
            label="Afternoon — on the water",
            suggested_time=_AFTERNOON,
            intent_key="on_the_water",
            slots=dict(area_slots),
            today=plan_date,
            empty_message=(
                "Nothing on-the-water in the catalog yet. Know a marina, rental, "
                "or launch? Add it."
            ),
        ),
        _evening_stop(db, today=plan_date),
    ]

    stops.sort(key=lambda s: s.sort_key)
    return Itinerary(plan_date=plan_date, title=title, stops=stops)
