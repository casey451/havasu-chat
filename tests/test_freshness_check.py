"""Tests for scripts/freshness_check.py.

Covers tz normalization, the newest-activity query (created_at vs scraped_at),
and the OK / STALE / MISSING grading with an injected ``now`` so the freshness
budget is exercised deterministically. Event rows are tagged with a unique
source per test and torn down in a finally, so nothing leaks into the catalog
tests that share the session DB.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Event
from scripts import freshness_check as fc


def _src() -> str:
    return f"test-fresh-{uuid.uuid4().hex[:8]}"


def _make_event(
    db,
    *,
    source: str,
    created_at: datetime,
    scraped_at: datetime | None = None,
) -> Event:
    suf = uuid.uuid4().hex[:6]
    ev = Event(
        title=f"Probe {suf}",
        normalized_title=f"probe {suf}",
        date=date(2026, 6, 6),
        start_time=time(18, 0),
        location_name="Test Venue",
        location_normalized="test venue",
        description="freshness probe",
        source=source,
        created_at=created_at,
        scraped_at=scraped_at,
    )
    db.add(ev)
    return ev


def _cleanup(source: str) -> None:
    with SessionLocal() as db:
        db.execute(delete(Event).where(Event.source == source))
        db.commit()


# ---------------------------------------------------------------------------
# _to_naive_utc
# ---------------------------------------------------------------------------


def test_to_naive_utc_passes_through_naive() -> None:
    dt = datetime(2026, 6, 1, 12, 0, 0)
    assert fc._to_naive_utc(dt) == dt


def test_to_naive_utc_converts_aware_to_utc() -> None:
    aware = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    out = fc._to_naive_utc(aware)
    assert out == datetime(2026, 6, 1, 12, 0, 0)
    assert out.tzinfo is None


def test_to_naive_utc_none() -> None:
    assert fc._to_naive_utc(None) is None


# ---------------------------------------------------------------------------
# newest_activity
# ---------------------------------------------------------------------------


def test_newest_activity_none_when_no_rows() -> None:
    with SessionLocal() as db:
        assert fc.newest_activity(db, _src()) is None


def test_newest_activity_picks_latest_created_across_rows() -> None:
    source = _src()
    try:
        with SessionLocal() as db:
            _make_event(db, source=source, created_at=datetime(2026, 6, 1, 8, 0, 0))
            _make_event(db, source=source, created_at=datetime(2026, 6, 3, 9, 0, 0))
            db.commit()
        with SessionLocal() as db:
            assert fc.newest_activity(db, source) == datetime(2026, 6, 3, 9, 0, 0)
    finally:
        _cleanup(source)


def test_newest_activity_scraped_at_counts_when_newer_than_created() -> None:
    """A re-seen event advances scraped_at without a new created_at; that still
    counts as activity (this is the merge path in app/events/dedup.py)."""
    source = _src()
    try:
        with SessionLocal() as db:
            _make_event(
                db,
                source=source,
                created_at=datetime(2026, 6, 1, 8, 0, 0),
                scraped_at=datetime(2026, 6, 5, 8, 0, 0, tzinfo=UTC),
            )
            db.commit()
        with SessionLocal() as db:
            freshest = fc.newest_activity(db, source)
        assert freshest is not None
        # scraped_at (Jun 5) must win over created_at (Jun 1), give or take the
        # America/Phoenix round-trip on the TZAware column.
        assert freshest > datetime(2026, 6, 3, 0, 0, 0)
    finally:
        _cleanup(source)


# ---------------------------------------------------------------------------
# evaluate -- OK / STALE / MISSING grading
# ---------------------------------------------------------------------------


def _check(source: str, max_age_hours: float = 120.0) -> fc.SourceCheck:
    return fc.SourceCheck(
        label="Test pipeline", source=source, cadence="test", max_age_hours=max_age_hours
    )


def test_evaluate_ok_when_fresh() -> None:
    source = _src()
    now = datetime(2026, 6, 5, 12, 0, 0)
    try:
        with SessionLocal() as db:
            _make_event(db, source=source, created_at=datetime(2026, 6, 5, 6, 0, 0))  # 6h ago
            db.commit()
        with SessionLocal() as db:
            results = fc.evaluate(db, [_check(source)], now=now)
        assert len(results) == 1
        assert results[0].status == "OK"
        assert results[0].age_hours == pytest.approx(6.0, abs=0.01)
    finally:
        _cleanup(source)


def test_evaluate_stale_when_past_budget() -> None:
    source = _src()
    now = datetime(2026, 6, 15, 12, 0, 0)
    try:
        with SessionLocal() as db:
            # 10 days old, budget is 120h (5 days).
            _make_event(db, source=source, created_at=datetime(2026, 6, 5, 12, 0, 0))
            db.commit()
        with SessionLocal() as db:
            results = fc.evaluate(db, [_check(source)], now=now)
        assert results[0].status == "STALE"
    finally:
        _cleanup(source)


def test_evaluate_missing_when_no_rows() -> None:
    source = _src()
    now = datetime(2026, 6, 5, 12, 0, 0)
    with SessionLocal() as db:
        results = fc.evaluate(db, [_check(source)], now=now)
    assert results[0].status == "MISSING"
    assert results[0].freshest is None
    assert results[0].age_hours is None


def test_evaluate_boundary_just_inside_budget_is_ok() -> None:
    source = _src()
    now = datetime(2026, 6, 6, 12, 0, 0)
    try:
        with SessionLocal() as db:
            # Exactly 119h old, budget 120h -> OK.
            _make_event(db, source=source, created_at=datetime(2026, 6, 1, 13, 0, 0))
            db.commit()
        with SessionLocal() as db:
            results = fc.evaluate(db, [_check(source, max_age_hours=120.0)], now=now)
        assert results[0].status == "OK"
    finally:
        _cleanup(source)


def test_configured_sources_match_live_workflow_strings() -> None:
    """Guard against drift: the configured sources must be the exact strings the
    scheduled *_pull.py workflows write (not the app/events/scrapers keys)."""
    configured = {c.source for c in fc.SOURCE_CHECKS}
    assert configured == {"river_scene_import", "go_lake_havasu"}
