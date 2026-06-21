"""Lake Havasu City local time (America/Phoenix, no DST). Phase 6.4."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

LAKE_HAVASU_TZ = ZoneInfo("America/Phoenix")


def now_lake_havasu() -> datetime:
    """Current wall-clock time in Lake Havasu City."""
    return datetime.now(LAKE_HAVASU_TZ)


def to_lake_naive(dt: datetime) -> datetime:
    """Lake Havasu (America/Phoenix) wall-clock as a NAIVE datetime.

    A tz-aware datetime is converted into Phoenix and then stripped of tzinfo; a
    naive datetime is assumed to already be Phoenix wall-clock (event date/time
    columns carry no tz). Use this to compare ``now`` against the naive
    :func:`occurrence_end_dt` so the answer is the same whether ``now`` arrives
    as Phoenix-aware, UTC-aware, or naive — never a ``utcnow()`` mismatch.
    """
    if dt.tzinfo is not None:
        return dt.astimezone(LAKE_HAVASU_TZ).replace(tzinfo=None)
    return dt.replace(tzinfo=None)


def occurrence_end_dt(
    day: date,
    start_time: time | None,
    end_time: time | None,
    *,
    default_minutes: int = 120,
) -> datetime | None:
    """Naive America/Phoenix wall-clock END datetime for an occurrence on ``day``.

    The single source of truth for "when does this event end?" used by every
    past/upcoming decision (home-feed muting, the event-detail "passed" banner,
    and /events-ui), so they can never disagree. Event date/time columns are
    stored as Lake Havasu (America/Phoenix) wall-clock with no per-row tz, so the
    naive datetime this returns must be compared against ``now`` in Phoenix
    wall-clock (``now_lake_havasu().replace(tzinfo=None)``), never ``utcnow()``.

    Handles the cross-midnight convention some sources use (the live "Motor
    Madness" bug): an ``end_time`` at or before the start — most importantly the
    ``00:00`` an "all-afternoon/evening" listing carries — means the event ends
    the FOLLOWING day, not at 00:00 that same morning. Without this, a 1 PM start
    / 00:00 end event reads as ~13 hours past before it has even begun.

    Returns ``None`` only when there is neither a start nor an end time (fully
    time-TBD). With a known start but no ``end_time``, falls back to
    ``start + default_minutes``.
    """
    if start_time is None and end_time is None:
        return None
    start_ref = start_time or time(0, 0)
    if end_time is not None:
        end_dt = datetime.combine(day, end_time)
        if end_dt <= datetime.combine(day, start_ref):
            end_dt += timedelta(days=1)  # crosses midnight (incl. 00:00 end)
        return end_dt
    return datetime.combine(day, start_ref) + timedelta(minutes=default_minutes)


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
