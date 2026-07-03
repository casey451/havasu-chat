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
    # Source-parity fix (2026-07-03): recurrence is decided by actual recurrence
    # DATA (rrule/rdate), NOT the bare ``is_recurring`` flag. ~266 rows carry
    # ``is_recurring=True`` with no rrule and no rdate; the old flag-based check
    # sent them down the expansion branch, which then produced ZERO occurrences
    # (empty rrule + empty rdate) and dropped them off the calendar entirely.
    # Ignoring the data-less flag makes them fall through to the single-date
    # branch and render on their stored date. This render-time fix covers both
    # existing and future rows; ``normalize_recurrence_flag`` additionally lets a
    # dry-run cleanup clear the stray flag at the data layer.
    return bool(event.rrule or event.rdate)


def normalize_recurrence_flag(
    *, is_recurring: bool, rrule: str | None, rdate: list[str] | None
) -> bool:
    """Return a truthful ``is_recurring`` flag: True only with real recurrence
    data (rrule or rdate). Call at ingest so no new row can carry the flag with
    no data — the state that dropped ~266 events off the calendar. Idempotent.
    """
    return bool(is_recurring and (rrule or rdate))


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

    Persisted recurrence data is known-messy (that is what N1 is about), so every
    parse here is defensive: a malformed ``rrule`` / ``exdate`` / ``rdate`` token
    is skipped, never raised. If the recurrence data can't be evaluated at all,
    the event degrades to one-off semantics (its ``event.date``) so the detail
    page still renders — this function must never raise into ``_display_date`` /
    ``_event_is_past`` and 500 the page.
    """
    if not _event_is_recurring(event):
        return event.date if event.date >= on_or_after else None

    # EXDATE: skip any token that isn't a parseable date rather than raising.
    excluded: set[date] = set()
    for x in event.exdate or []:
        try:
            excluded.add(date.fromisoformat(str(x)[:10]))
        except (ValueError, TypeError):
            continue

    best: date | None = None
    rule_ok = True  # False if an rrule was present but could not be evaluated

    rule_body = (event.rrule or "").strip()
    if rule_body:
        try:
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
        except (ValueError, TypeError):
            # Malformed rrule (or a NULL start_time on a recurring row): can't
            # evaluate the rule. Fall through to RDATE / the one-off fallback.
            rule_ok = False

    for extra in event.rdate or []:
        try:
            d = date.fromisoformat(str(extra)[:10])
        except (ValueError, TypeError):
            continue
        if d >= on_or_after and d not in excluded and (best is None or d < best):
            best = d

    if best is None and not rule_ok:
        # Recurrence data was malformed and yielded nothing — degrade to one-off
        # semantics so the page renders (anchor date), never raising.
        return event.date if event.date is not None and event.date >= on_or_after else None

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
