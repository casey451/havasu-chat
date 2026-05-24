"""Phase 9b — EVENT_AUTO_APPROVE_SOURCES allowlist."""

from __future__ import annotations

from datetime import date, time

from app.contrib.approval_service import (
    auto_approve_event_sources,
    should_auto_approve_event,
)
from app.db.models import Contribution


def _contrib(**kwargs) -> Contribution:
    c = Contribution(
        entity_type="event",
        submission_name="Show",
        status="pending",
        source="chamber",
        event_date=date(2026, 6, 1),
        event_time_start=time(18, 0),
    )
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


def test_chamber_auto_approves() -> None:
    assert should_auto_approve_event(_contrib(source="chamber"))


def test_lhc_library_manual() -> None:
    assert not should_auto_approve_event(_contrib(source="lhc_library"))


def test_incomplete_rejected() -> None:
    assert not should_auto_approve_event(_contrib(event_date=None))


def test_default_sources_include_river_scene() -> None:
    assert "river_scene" in auto_approve_event_sources()
