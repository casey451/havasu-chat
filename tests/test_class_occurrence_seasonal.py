"""Seasonal Schedule window: a schedule with start_date/end_date only renders
within its season (2026-07-03). Null bounds mean unbounded (existing behavior).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time

from app.db.database import SessionLocal
from app.db.models import Entity, Schedule
from app.events.class_occurrences import class_occurrences_in_window


def _now() -> datetime:
    return datetime.now(UTC)


def _seed(days, *, start_date=None, end_date=None) -> tuple[str, str]:
    suf = uuid.uuid4().hex[:8]
    name = f"Seasonal Pool {suf}"
    title = f"Open Swim {suf}"
    with SessionLocal() as db:
        ent = Entity(
            entity_type="venue", slug=f"venue-{suf}", name=name,
            source="test-seasonal", is_active=True,
        )
        db.add(ent)
        db.commit()
        db.add(
            Schedule(
                entity_id=ent.id, schedule_type="recurring", days_of_week=days,
                start_time=time(12, 0), end_time=time(16, 0), notes=title,
                start_date=start_date, end_date=end_date,
                created_at=_now(), updated_at=_now(),
            )
        )
        db.commit()
    return name, title


def _titles(name: str, ws: date, we: date) -> list[date]:
    with SessionLocal() as db:
        return sorted(
            o.date for o in class_occurrences_in_window(db, window_start=ws, window_end=we)
            if o.venue == name
        )


def test_end_date_stops_rendering_after_season() -> None:
    name, _ = _seed(["monday", "wednesday", "friday"], end_date=date(2026, 7, 31))
    # July: renders
    jul = _titles(name, date(2026, 7, 6), date(2026, 7, 10))
    assert date(2026, 7, 6) in jul and date(2026, 7, 8) in jul and date(2026, 7, 10) in jul
    # August (past end_date): nothing
    aug = _titles(name, date(2026, 8, 1), date(2026, 8, 31))
    assert aug == []


def test_start_date_gates_before_season() -> None:
    name, _ = _seed(["monday"], start_date=date(2026, 8, 1))
    # before the season starts: nothing
    assert _titles(name, date(2026, 7, 1), date(2026, 7, 31)) == []
    # within the season: renders
    assert date(2026, 8, 3) in _titles(name, date(2026, 8, 1), date(2026, 8, 31))


def test_null_bounds_unbounded() -> None:
    name, _ = _seed(["tuesday"])  # no start/end -> always
    assert _titles(name, date(2026, 12, 1), date(2026, 12, 31))  # renders far out
