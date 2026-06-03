"""Staleness labels for conditions tiles (Phase 8a)."""

from __future__ import annotations

from datetime import datetime


def staleness_label(
    fetched_at: datetime, now: datetime, *, stale_after_hours: int = 2
) -> tuple[str, bool]:
    """``(human label, is_stale)`` for a conditions tile.

    ``stale_after_hours`` lets slow feeds opt out of the default 2h threshold —
    e.g. the roughly-daily gas feed passes a full-day value so a fresh fetch
    doesn't read "stale" (G-2). Feeds that update often keep the 2h default.
    """
    delta = now - fetched_at
    minutes = max(0, int(delta.total_seconds() / 60))
    if minutes < 60:
        return f"Updated {minutes} min ago", False
    hours = minutes // 60
    is_stale = hours >= stale_after_hours
    if hours < 24:
        return f"Updated >{hours}h ago", is_stale
    return f"Updated {delta.days}d ago", is_stale
