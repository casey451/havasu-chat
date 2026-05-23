"""RRULE expansion helpers (Phase 9a)."""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Iterable

from dateutil.rrule import rrulestr

from app.db.models import Event

_UNTIL_RE = re.compile(r"UNTIL=(\d{8})T", re.IGNORECASE)


def parsed_until_from_rrule(rrule: str | None) -> date | None:
    """Parse UNTIL=YYYYMMDD from an RRULE string, if present."""
    if not rrule:
        return None
    m = _UNTIL_RE.search(rrule)
    if not m:
        return None
    try:
        return date(int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:8]))
    except ValueError:
        return None


def _event_is_recurring(event: Event) -> bool:
    return bool(event.rrule or event.rdate or event.is_recurring)


def expand_event(
    event: Event,
    *,
    window_start: date,
    window_end: date,
    cap: int = 100,
) -> list[date]:
    """Return occurrence dates within [window_start, window_end] for one event."""
    if not _event_is_recurring(event):
        if window_start <= event.date <= window_end:
            return [event.date]
        return []

    dtstart = datetime.combine(event.date, event.start_time)

    occurrences: list[date] = []
    rule_body = (event.rrule or "").strip()
    if rule_body:
        if rule_body.upper().startswith("RRULE:"):
            rule_body = rule_body.split(":", 1)[1].strip()
        rule_text = f"DTSTART:{dtstart.strftime('%Y%m%dT%H%M%S')}\nRRULE:{rule_body}"
        rule = rrulestr(rule_text, ignoretz=True)
        win_start = datetime.combine(window_start, time.min)
        win_end = datetime.combine(window_end, time.max)
        for occ in rule.between(win_start, win_end, inc=True):
            d = occ.date()
            if d not in occurrences:
                occurrences.append(d)
            if len(occurrences) > cap:
                raise ValueError(
                    f"event.id={event.id} expansion exceeded cap={cap}; "
                    f"check rrule={event.rrule!r}"
                )

    for extra in event.rdate or []:
        d = date.fromisoformat(str(extra)[:10])
        if window_start <= d <= window_end and d not in occurrences:
            occurrences.append(d)
            if len(occurrences) > cap:
                raise ValueError(
                    f"event.id={event.id} expansion exceeded cap={cap}; check rdate"
                )

    excluded = {date.fromisoformat(str(x)[:10]) for x in (event.exdate or [])}
    occurrences = [d for d in occurrences if d not in excluded]
    occurrences.sort()
    return occurrences


def occurrences_in_window(
    events: Iterable[Event],
    *,
    window_start: date,
    window_end: date,
    cap: int = 100,
) -> list[tuple[Event, date]]:
    """Expand multiple events; sort by date, start_time, normalized_title."""
    flat: list[tuple[Event, date]] = []
    for ev in events:
        for d in expand_event(ev, window_start=window_start, window_end=window_end, cap=cap):
            flat.append((ev, d))
    flat.sort(key=lambda pair: (pair[1], pair[0].start_time, pair[0].normalized_title))
    return flat
