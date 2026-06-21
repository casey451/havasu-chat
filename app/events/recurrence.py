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
                    f"event.id={event.id} expansion exceeded cap={cap}; check rrule={event.rrule!r}"
                )

    for extra in event.rdate or []:
        d = date.fromisoformat(str(extra)[:10])
        if window_start <= d <= window_end and d not in occurrences:
            occurrences.append(d)
            if len(occurrences) > cap:
                raise ValueError(f"event.id={event.id} expansion exceeded cap={cap}; check rdate")

    excluded = {date.fromisoformat(str(x)[:10]) for x in (event.exdate or [])}
    occurrences = [d for d in occurrences if d not in excluded]
    occurrences.sort()
    return occurrences


def next_occurrence(event: Event, *, on_or_after: date) -> date | None:
    """The first occurrence on or after ``on_or_after``, or None if the series
    has no future date.

    A recurring event stores ``event.date`` as the RRULE *anchor* (for the
    senior-center series that's a 2024 ``Monday, January 1`` seed), never the
    upcoming date a visitor should see. The day/index views expand the rule to
    real dates; the detail page must do the same so it shows the next live
    occurrence instead of the anchor (the N1 "January 1 / This event has passed"
    bug). For a one-off, returns ``event.date`` when it is not already past.
    """
    if not _event_is_recurring(event):
        return event.date if event.date >= on_or_after else None

    excluded = {date.fromisoformat(str(x)[:10]) for x in (event.exdate or [])}
    best: date | None = None

    rule_body = (event.rrule or "").strip()
    if rule_body:
        if rule_body.upper().startswith("RRULE:"):
            rule_body = rule_body.split(":", 1)[1].strip()
        dtstart = datetime.combine(event.date, event.start_time)
        rule_text = f"DTSTART:{dtstart.strftime('%Y%m%dT%H%M%S')}\nRRULE:{rule_body}"
        rule = rrulestr(rule_text, ignoretz=True)
        cursor = datetime.combine(on_or_after, time.min)
        inc = True
        # Bounded walk so an EXDATE'd occurrence is skipped without looping
        # forever; a year of candidates covers any real cadence (annual incl.).
        for _ in range(370):
            nxt = rule.after(cursor, inc=inc)
            if nxt is None:
                break
            d = nxt.date()
            if d not in excluded:
                best = d
                break
            cursor = nxt
            inc = False

    for extra in event.rdate or []:
        d = date.fromisoformat(str(extra)[:10])
        if d >= on_or_after and d not in excluded and (best is None or d < best):
            best = d

    return best


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
