"""Civic meetings bucket to City & Government, never Music & nightlife.

Phase 2.4 (FIX_SPEC_2026-06-23) — verify-first. Live capture showed "Board of
Adjustment Meeting" under Music & nightlife. Tracing into code: ``is_civic`` is
checked BEFORE the music tier in ``group_for_tier`` (event_buckets.py:145), the
"aDJustment" → music false-positive is guarded by word-boundary matching, and
the day view routes through ``_group_for`` → ``_event_tier`` → ``group_for_tier``.
So the live miss was the stale deploy (or an untagged source). This locks the
exact live title end-to-end through the day-view router.
"""

from __future__ import annotations

from app.home.event_buckets import is_civic
from app.home.events_views import _group_for


def test_board_of_adjustment_meeting_is_civic() -> None:
    assert is_civic("Board of Adjustment Meeting")


def test_board_of_adjustment_meeting_routes_to_civic_not_music() -> None:
    """End-to-end through the day-view bucket router."""
    g = _group_for(
        title="Board of Adjustment Meeting", tags=None, featured=False, recurring=False
    )
    assert g == "civic", g


def test_civic_tag_alone_routes_even_with_bland_title() -> None:
    g = _group_for(
        title="Regular Session", tags=["civic", "government", "meeting"],
        featured=False, recurring=False,
    )
    assert g == "civic", g
