"""Lake Havasu City local time (America/Phoenix, no DST). Phase 6.4."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

LAKE_HAVASU_TZ = ZoneInfo("America/Phoenix")


def now_lake_havasu() -> datetime:
    """Current wall-clock time in Lake Havasu City."""
    return datetime.now(LAKE_HAVASU_TZ)


def format_now_lake_havasu(dt: datetime | None = None) -> str:
    """Human-readable stamp for Tier 3 user payload, e.g. ``Tuesday, April 21, 2026, 2:47 PM``."""
    d = dt if dt is not None else now_lake_havasu()
    # %-I is Unix-only; strip leading zero from hour on Windows.
    base = d.strftime("%A, %B %d, %Y, %I:%M %p")
    parts = base.rsplit(", ", 1)
    if len(parts) == 2:
        date_part, time_part = parts
        if time_part.startswith("0") and len(time_part) > 1 and time_part[1].isdigit():
            time_part = time_part[1:]
        return f"{date_part}, {time_part}"
    return base
