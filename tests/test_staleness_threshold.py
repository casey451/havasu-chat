"""G-2 — staleness threshold is configurable so daily feeds don't read 'stale'."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.conditions.constants import GAS_STALE_AFTER_HOURS
from app.conditions.staleness import staleness_label

_NOW = datetime(2026, 6, 3, 12, 0, 0)


def test_default_threshold_marks_two_hours_stale() -> None:
    label, stale = staleness_label(_NOW - timedelta(hours=3), _NOW)
    assert stale is True
    assert ">3h" in label


def test_gas_threshold_keeps_recent_daily_feed_fresh() -> None:
    # A gas feed fetched 5h ago is NOT stale under the daily threshold (was under 2h).
    _, stale = staleness_label(
        _NOW - timedelta(hours=5), _NOW, stale_after_hours=GAS_STALE_AFTER_HOURS
    )
    assert stale is False


def test_gas_threshold_one_day_old_is_fresh_but_past_it_is_stale() -> None:
    _, fresh = staleness_label(
        _NOW - timedelta(hours=25), _NOW, stale_after_hours=GAS_STALE_AFTER_HOURS
    )
    assert fresh is False
    _, stale = staleness_label(
        _NOW - timedelta(hours=30), _NOW, stale_after_hours=GAS_STALE_AFTER_HOURS
    )
    assert stale is True


def test_under_an_hour_is_never_stale() -> None:
    label, stale = staleness_label(_NOW - timedelta(minutes=10), _NOW)
    assert stale is False
    assert "10 min ago" in label
