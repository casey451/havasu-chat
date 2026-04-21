"""Structured hours from Google Places + open-now checks (Phase 5.6).

Overnight periods (close on a different calendar day than open in Places ``day``)
are split into two segments: end-of-open-day ``23:59`` and start-of-close-day
``00:00``–``close``, so each weekday bucket only contains same-day ranges.

**Close time convention:** ``is_open_at`` treats the closing ``HH:MM`` as **inclusive**
(the business is still considered open at exactly that minute).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo

    LAKE_HAVASU_TZ = ZoneInfo("America/Phoenix")
except Exception:  # pragma: no cover — missing tzdata / IANA (e.g. some Windows installs)
    # Arizona: no DST; UTC−7 year-round (same wall clock as America/Phoenix).
    LAKE_HAVASU_TZ = timezone(timedelta(hours=-7))

# Google Places ``periods[].open.day``: 0=Sunday … 6=Saturday
_GOOGLE_DAY_TO_KEY: tuple[str, ...] = (
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
)

# Python ``weekday()`` Monday=0 … Sunday=6 → our lowercase keys (same order as Tier 2)
_PYTHON_WEEKDAY_TO_KEY: tuple[str, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def _hm(point: dict[str, Any] | None) -> str | None:
    if not isinstance(point, dict):
        return None
    h = int(point.get("hour", 0))
    m = int(point.get("minute", 0))
    return f"{h:02d}:{m:02d}"


def _append_segment(out: dict[str, list[dict[str, str]]], day_key: str, open_s: str, close_s: str) -> None:
    if day_key not in out:
        out[day_key] = []
    out[day_key].append({"open": open_s, "close": close_s})


def places_hours_to_structured(places_regular_opening_hours: dict) -> dict:
    """Convert Google Places ``regular_opening_hours`` → structured weekday dict.

    Returns ``{}`` if conversion fails or input is malformed.
    """
    if not isinstance(places_regular_opening_hours, dict):
        return {}
    periods = places_regular_opening_hours.get("periods")
    if not isinstance(periods, list) or not periods:
        return {}

    out: dict[str, list[dict[str, str]]] = {}

    for period in periods:
        if not isinstance(period, dict):
            continue
        o = period.get("open")
        if not isinstance(o, dict) or "day" not in o:
            continue
        try:
            od = int(o["day"]) % 7
        except (TypeError, ValueError):
            continue
        open_s = _hm(o)
        if open_s is None:
            continue
        day_open = _GOOGLE_DAY_TO_KEY[od]

        c = period.get("close")
        if not isinstance(c, dict) or "day" not in c:
            # Open with no close → treat as all day (24/7 style single anchor)
            _append_segment(out, day_open, "00:00", "23:59")
            continue
        try:
            cd = int(c["day"]) % 7
        except (TypeError, ValueError):
            continue
        close_s = _hm(c)
        if close_s is None:
            continue
        day_close = _GOOGLE_DAY_TO_KEY[cd]

        if od == cd:
            _append_segment(out, day_open, open_s, close_s)
            continue

        # Overnight or cross-midnight: split across two weekday keys.
        _append_segment(out, day_open, open_s, "23:59")
        _append_segment(out, day_close, "00:00", close_s)

    return dict(out)


def is_open_at(hours_structured: dict, as_of: datetime) -> bool:
    """Return True if ``hours_structured`` indicates open at ``as_of`` (Lake Havasu local wall clock).

    ``as_of`` may be naive (interpreted as America/Phoenix) or aware (converted to Phoenix).
    Returns False for malformed input, missing weekday, or empty segments.
    """
    if not isinstance(hours_structured, dict) or not hours_structured:
        return False

    if as_of.tzinfo is None:
        local = as_of.replace(tzinfo=LAKE_HAVASU_TZ)
    else:
        local = as_of.astimezone(LAKE_HAVASU_TZ)

    wk = _PYTHON_WEEKDAY_TO_KEY[local.weekday()]
    segs = hours_structured.get(wk)
    if not isinstance(segs, list) or not segs:
        return False

    cur = f"{local.hour:02d}:{local.minute:02d}"

    for seg in segs:
        if not isinstance(seg, dict):
            continue
        o = seg.get("open")
        cl = seg.get("close")
        if not isinstance(o, str) or not isinstance(cl, str) or len(o) != 5 or len(cl) != 5:
            continue
        if o <= cur <= cl:
            return True
    return False
