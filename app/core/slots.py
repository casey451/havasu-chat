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
