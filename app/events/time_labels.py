"""Shared event time-label helpers (calendar redesign).

Two ingest realities make raw ``start_time`` rendering lie:

* WP-4 allows NULL times at ingest (never fabricate noon), and
* aggregator feeds without a time component land as a 00:00 start (the ingest
  fallback), so a bare midnight start with no real end time — or a
  zero-duration midnight-to-midnight span (allevents fills ``endDate`` with
  midnight too) — is "time unknown", not a real 12 AM event.

This module is the single definition of that contract so the home week strip,
the month grid, the events list, and the permalink all agree: unknown times
render as :data:`TIME_TBD_LABEL` (or are omitted) — never "12 AM" — and sort
*after* timed events.
"""

from __future__ import annotations

from datetime import time

TIME_TBD_LABEL = "Time TBD"


def is_time_tbd(start_time: time | None, end_time: time | None = None) -> bool:
    """True when the event has no real start time.

    A NULL start is unknown outright. A bare 00:00 start is the aggregator/OCR
    ingest fallback for a MISSING start. It counts as a *real* midnight start
    only for a genuine overnight event that ends in the small hours (e.g. a
    midnight–2 AM party). A daytime end (a flyer that listed only an end time,
    so the start defaulted to 00:00 — "Creative Mondays 00:00–4:45 PM"), the
    00:00–23:59 all-day marker, a midnight-to-midnight zero span, or no end at
    all all mean the midnight start is bogus → TBD (F5b: stop rendering these
    as "12 am" in chat / on the calendar).
    """
    if start_time is None:
        return True
    if start_time.hour != 0 or start_time.minute != 0:
        return False
    if end_time is None:
        return True
    return not (time(0, 0) < end_time < time(6, 0))


def format_short_time(t: time) -> str:
    """12-hour label without the leading-zero / noon / midnight bugs.

    ``08:00`` -> "8 AM", ``18:30`` -> "6:30 PM", ``12:00`` -> "12 PM",
    ``00:15`` -> "12:15 AM". Cross-platform (no ``%-I``/``%#I`` divergence).
    """
    hour12 = t.hour % 12 or 12
    meridiem = "AM" if t.hour < 12 else "PM"
    if t.minute:
        return f"{hour12}:{t.minute:02d} {meridiem}"
    return f"{hour12} {meridiem}"


def short_time_label(start_time: time | None, end_time: time | None = None) -> str | None:
    """Short 12-hour label, or ``None`` when the time is unknown.

    Callers omit the time (or render :data:`TIME_TBD_LABEL`) on ``None`` —
    never the fabricated "12 AM" the raw midnight fallback used to produce.
    """
    if is_time_tbd(start_time, end_time):
        return None
    return format_short_time(start_time)


def time_sort_key(start_time: time | None, end_time: time | None = None) -> tuple[int, time]:
    """Chronological sort key that places time-TBD events after timed ones."""
    if is_time_tbd(start_time, end_time):
        return (1, time(0, 0))
    return (0, start_time)
