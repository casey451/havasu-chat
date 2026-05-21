"""Staleness labels for conditions tiles (Phase 8a)."""

from __future__ import annotations

from datetime import datetime


def staleness_label(fetched_at: datetime, now: datetime) -> tuple[str, bool]:
    delta = now - fetched_at
    minutes = max(0, int(delta.total_seconds() / 60))
    if minutes < 60:
        return f"Updated {minutes} min ago", False
    hours = minutes // 60
    if hours < 24:
        is_stale = hours >= 2
        return f"Updated >{hours}h ago", is_stale
    return f"Updated {delta.days}d ago", True
