"""Pure parsing helpers for the Movies Havasu scraper.

Kept browser-free and dependency-light (stdlib only) so they're unit-tested in
the normal suite. The Playwright DOM scraping lives in
``scripts/scrape_movies_havasu.py`` (run only in CI, never imported by the app).
"""

from __future__ import annotations

import re
from datetime import date, time, timedelta

_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*([AaPp])\.?[Mm]")
_RUNTIME_RE = re.compile(r"(?:(\d+)\s*hr)?\s*(?:(\d+)\s*min)?", re.IGNORECASE)
_DAYNUM_RE = re.compile(r"(\d{1,2})")


def parse_clock_time(text: str | None) -> time | None:
    """'7:00PM' / '11:00 AM' / '12:30AM' -> a ``time`` (24h). None if unparseable."""
    if not text:
        return None
    m = _TIME_RE.search(text)
    if not m:
        return None
    hour = int(m.group(1)) % 12
    minute = int(m.group(2))
    if m.group(3).upper() == "P":
        hour += 12
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def parse_runtime_minutes(text: str | None) -> int | None:
    """'2 hr 2 min' -> 122, '1 hr' -> 60, '95 min' -> 95. None if no digits."""
    if not text:
        return None
    m = _RUNTIME_RE.search(text)
    if not m or (m.group(1) is None and m.group(2) is None):
        return None
    hours = int(m.group(1)) if m.group(1) else 0
    mins = int(m.group(2)) if m.group(2) else 0
    total = hours * 60 + mins
    return total or None


def resolve_strip_dates(labels: list[str], *, today: date) -> list[date]:
    """Map date-strip labels ('Fri19', 'Sat20', ... 'Wed1') to real dates.

    The strip lists consecutive upcoming days starting at/after today. We read
    each label's day-of-month and walk a cursor forward to the next date with
    that day number — robust across month boundaries (June 30 -> July 1) without
    assuming the labels are strictly contiguous.
    """
    out: list[date] = []
    cursor = today
    for label in labels:
        m = _DAYNUM_RE.search(label or "")
        if not m:
            continue
        day_num = int(m.group(1))
        d = cursor
        for _ in range(370):  # bound the search to ~a year
            if d.day == day_num:
                break
            d += timedelta(days=1)
        else:
            continue
        out.append(d)
        cursor = d + timedelta(days=1)
    return out
