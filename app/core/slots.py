"""Date-range extraction from user text (the survivor of the Phase 8.5 slots)."""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, timedelta
from typing import TypedDict

from app.core.timezone import now_lake_havasu

DAY_NAMES = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

class DateRange(TypedDict):
    start: date
    end: date


_MONTH_NAMES = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

_MONTH_DAY_RE = re.compile(
    r"\b(" + "|".join(sorted(_MONTH_NAMES, key=len, reverse=True)) + r")\.?\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?(?!\s*(?:am|pm|:|\d))"
    r"(?:,?\s*(20\d{2}))?\b"
)


def _next_weekday(start_date: date, weekday: int, allow_today: bool) -> date:
    days_ahead = (weekday - start_date.weekday()) % 7
    if days_ahead == 0 and not allow_today:
        days_ahead = 7
    return start_date + timedelta(days=days_ahead)


def extract_date_range(text: str) -> DateRange | None:
    lowered = text.lower()
    # Lake Havasu (America/Phoenix) date, not the server-local (UTC) date —
    # date.today() on a UTC host rolls "today"/"tomorrow" a day early after
    # ~5 PM local. (P1-8)
    today = now_lake_havasu().date()

    # "First Friday" is a recurring event name, not "next Friday" as a day filter.
    if "first friday" in lowered:
        return None

    if "today" in lowered or "tonight" in lowered:
        return {"start": today, "end": today}
    if "tomorrow" in lowered:
        t = today + timedelta(days=1)
        return {"start": t, "end": t}

    if "this weekend" in lowered:
        saturday = _next_weekday(today, 5, allow_today=True)
        sunday = saturday + timedelta(days=1)
        return {"start": saturday, "end": sunday}

    # "this week" check must come after "this weekend" (substring).
    if "this week" in lowered:
        sunday = _next_weekday(today, 6, allow_today=True)
        return {"start": today, "end": sunday}

    if "next week" in lowered:
        monday = _next_weekday(today, 0, allow_today=False)
        if monday <= today:
            monday += timedelta(days=7)
        return {"start": monday, "end": monday + timedelta(days=6)}

    if "next month" in lowered:
        year = today.year + (1 if today.month == 12 else 0)
        month = 1 if today.month == 12 else today.month + 1
        last_day = monthrange(year, month)[1]
        return {"start": date(year, month, 1), "end": date(year, month, last_day)}

    if "this month" in lowered:
        last_day = monthrange(today.year, today.month)[1]
        return {"start": today, "end": date(today.year, today.month, last_day)}

    # "July 25" / "july 25th, 2026" — a full calendar day. Checked BEFORE the
    # weekday loop so "Friday, July 25" resolves to the 25th, not to next
    # Friday (same priority the tier2 parser prompt specifies: a full specific
    # calendar day beats its day-of-week word). Yearless dates resolve to the
    # next future occurrence. The (?!\s*(?:am|pm|:)) guard keeps clock
    # phrasings like "open until may 8pm" from reading as May 8.
    m = _MONTH_DAY_RE.search(lowered)
    if m:
        month = _MONTH_NAMES[m.group(1)]
        day = int(m.group(2))
        year_str = m.group(3)
        try:
            if year_str:
                target = date(int(year_str), month, day)
                if target >= today:
                    return {"start": target, "end": target}
            else:
                target = date(today.year, month, day)
                if target < today:
                    target = date(today.year + 1, month, day)
                return {"start": target, "end": target}
        except ValueError:
            pass

    for day_name, weekday in DAY_NAMES.items():
        if day_name in lowered:
            target = _next_weekday(today, weekday, allow_today=True)
            return {"start": target, "end": target}

    # "Saturday at 9" style — weekday already caught
    m = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", lowered)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            target = date(y, mo, d)
            if target >= today:
                return {"start": target, "end": target}
        except ValueError:
            pass

    return None


# (Everything else this module carried — activity/audience/location extraction,
# the merge_* slot combinators, search-label/broaden helpers, QUERY_SYNONYMS —
# was deleted 2026-07-02: it belonged to the Track-A search pipeline removed in
# Backlog #36; only its own tests kept it green. extract_date_range stays: the
# intent classifier/resolver use it on every chat request.)
