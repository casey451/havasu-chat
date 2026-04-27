"""
Parse the value after ``Date:`` in RiverScene-style submission notes.

See ``docs/multiday-events-step5a-survey-report.md`` for supported shapes.
"""

from __future__ import annotations

import calendar
import re
from datetime import date

# Same-month range: day–day with en-dash, ASCII hyphen, or em-dash between day numbers.
_RANGE_SEP = r"[–\-—]"

# Full line after optional "Date:" prefix: single month-day-year, or same-month range.
_SINGLE = re.compile(r"^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})\s*$")
_RANGE = re.compile(
    rf"^([A-Za-z]+)\s+(\d{{1,2}})\s*{_RANGE_SEP}\s*(\d{{1,2}}),\s*(\d{{4}})\s*$"
)
_DATE_PREFIX = re.compile(r"^\s*date:\s*", re.IGNORECASE)

_month_to_index: dict[str, int] = {
    n.lower(): i for i, n in enumerate(calendar.month_name) if n
}


def _month_num(name: str) -> int | None:
    return _month_to_index.get(name.strip().lower())


def _strip_date_prefix(line: str) -> str:
    """Drop leading ``Date:`` so callers may pass the full first line or the value only."""
    return _DATE_PREFIX.sub("", line).strip()


def parse_event_date_line(line: str) -> tuple[date, date | None] | None:
    """
    Parse a ``Date:`` line value (with or without ``Date:`` prefix).

    Returns ``(start, end)`` where ``end`` is ``None`` for a single calendar day, or the
    inclusive end date for a same-month multi-day range. Returns ``None`` if unparseable
    or out of scope (e.g. cross-month / two-segment lines).
    """
    core = _strip_date_prefix(line)
    if not core:
        return None

    rm = _RANGE.match(core)
    if rm:
        mon_s, d1s, d2s, ys = rm.group(1), rm.group(2), rm.group(3), rm.group(4)
        mon = _month_num(mon_s)
        if mon is None:
            return None
        y = int(ys)
        d1, d2 = int(d1s), int(d2s)
        try:
            start = date(y, mon, d1)
            end = date(y, mon, d2)
        except ValueError:
            return None
        if end < start:
            return None
        if end == start:
            return (start, None)
        return (start, end)

    sm = _SINGLE.match(core)
    if sm:
        mon_s, ds, ys = sm.group(1), sm.group(2), sm.group(3)
        mon = _month_num(mon_s)
        if mon is None:
            return None
        y, d = int(ys), int(ds)
        try:
            start = date(y, mon, d)
        except ValueError:
            return None
        return (start, None)

    return None
