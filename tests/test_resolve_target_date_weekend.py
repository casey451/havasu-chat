"""#4b: resolve_target_date anchors multi-day windows to the window start.

A "this weekend" query on a weekday previously fell through to today, so the
day-agenda rendered "Thursday's busy ..." for a Fri-Sun window.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.chat import component_builders as cb
from app.chat.tier2_schema import Tier2Filters


@pytest.fixture
def _thursday(monkeypatch: pytest.MonkeyPatch) -> None:
    class _D:
        @staticmethod
        def date() -> date:
            return date(2026, 6, 18)  # Thursday

    monkeypatch.setattr(cb, "now_lake_havasu", lambda: _D())


def test_this_weekend_targets_friday_not_today(_thursday: None) -> None:
    f = Tier2Filters(parser_confidence=0.9, time_window="this_weekend")
    assert cb.resolve_target_date(f) == date(2026, 6, 19)  # Friday, in-window


def test_this_week_targets_today(_thursday: None) -> None:
    f = Tier2Filters(parser_confidence=0.9, time_window="this_week")
    # this-week window starts today; the point is it no longer mis-falls-through.
    assert cb.resolve_target_date(f) == date(2026, 6, 18)


def test_today_window_unchanged(_thursday: None) -> None:
    f = Tier2Filters(parser_confidence=0.9, time_window="today")
    assert cb.resolve_target_date(f) == date(2026, 6, 18)
