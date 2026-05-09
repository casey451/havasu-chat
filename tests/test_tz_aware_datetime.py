"""Tests for ``app.db.types.TZAwareDateTime`` (Backlog #41a SQLite parity)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import StatementError

from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.models import Event, Provider, Sponsor, SponsorStatus


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _provider(**kwargs) -> Provider:
    return Provider(
        provider_name=kwargs.pop("provider_name", "TZ Test Provider"),
        category=kwargs.pop("category", "services"),
        **kwargs,
    )


def _aware_lake_havasu(dt_utc: datetime) -> datetime:
    """Expected ORM load shape: aware America/Phoenix for instant ``dt_utc``."""
    return dt_utc.astimezone(LAKE_HAVASU_TZ)


def test_aware_datetime_round_trips_aware(db) -> None:
    ts = datetime(2024, 7, 1, 18, 45, tzinfo=UTC)
    p = _provider(last_verified_at=ts)
    db.add(p)
    db.commit()
    db.refresh(p)
    assert p.last_verified_at is not None
    expected_aware = _aware_lake_havasu(ts)
    assert p.last_verified_at == expected_aware
    assert p.last_verified_at.tzinfo is not None
    assert p.last_verified_at.utcoffset() == ts.astimezone(LAKE_HAVASU_TZ).utcoffset()


def test_naive_datetime_loaded_from_sqlite_treated_as_utc(db) -> None:
    p = _provider(last_verified_at=None)
    db.add(p)
    db.flush()
    pid = p.id
    db.execute(
        text("UPDATE providers SET last_verified_at = :ts WHERE id = :id"),
        {"ts": "2020-06-15 14:30:00", "id": pid},
    )
    db.commit()
    loaded = db.get(Provider, pid)
    assert loaded is not None and loaded.last_verified_at is not None
    expected_instant_utc = datetime(2020, 6, 15, 14, 30, tzinfo=UTC)
    as_aware_local = loaded.last_verified_at
    assert as_aware_local.astimezone(UTC) == expected_instant_utc


def test_loaded_datetime_in_lake_havasu_tz(db) -> None:
    p = _provider(last_verified_at=None)
    db.add(p)
    db.flush()
    pid = p.id
    db.execute(
        text("UPDATE providers SET last_verified_at = :ts WHERE id = :id"),
        {"ts": "2019-03-10 08:00:00", "id": pid},
    )
    db.commit()
    loaded = db.get(Provider, pid)
    assert loaded is not None and loaded.last_verified_at is not None
    expected_aware = _aware_lake_havasu(datetime(2019, 3, 10, 8, 0, tzinfo=UTC))
    assert loaded.last_verified_at == expected_aware


def test_writing_naive_datetime_raises_valueerror(db) -> None:
    # SQLAlchemy wraps ValueError from bind processors as StatementError.
    with pytest.raises(StatementError, match="timezone-naive"):
        p = _provider(last_verified_at=datetime(2021, 1, 1, 12, 0, 0))
        db.add(p)
        db.flush()


def test_writing_none_round_trips_as_none(db) -> None:
    p = _provider(last_verified_at=None)
    db.add(p)
    db.commit()
    pid = p.id
    loaded = db.get(Provider, pid)
    assert loaded is not None
    assert loaded.last_verified_at is None


def test_provider_last_verified_at_uses_tzaware(db) -> None:
    ts = datetime(2025, 2, 2, 9, 15, tzinfo=UTC)
    p = _provider(last_verified_at=ts)
    db.add(p)
    db.commit()
    db.refresh(p)
    assert p.last_verified_at is not None
    assert p.last_verified_at == _aware_lake_havasu(ts)


def test_event_last_verified_at_uses_tzaware(db) -> None:
    ts = datetime(2025, 2, 2, 9, 15, tzinfo=UTC)
    today = date.today()
    ev = Event(
        title="TZ Test Event",
        normalized_title="tz test event",
        date=today,
        start_time=time(10, 0),
        location_name="Park",
        location_normalized="park",
        description="Twenty characters minimum here.",
        last_verified_at=ts,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    assert ev.last_verified_at is not None
    assert ev.last_verified_at == _aware_lake_havasu(ts)


def test_sponsor_starts_at_ends_at_use_tzaware(db) -> None:
    start = datetime(2025, 4, 1, 0, 0, tzinfo=UTC)
    end = datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)
    sp = Sponsor(
        name="Sponsor TZ Test",
        cta_url="https://example.com",
        status=SponsorStatus.DRAFT.value,
        starts_at=start,
        ends_at=end,
    )
    db.add(sp)
    db.commit()
    db.refresh(sp)
    assert sp.starts_at is not None and sp.ends_at is not None
    assert sp.starts_at == _aware_lake_havasu(start)
    assert sp.ends_at == _aware_lake_havasu(end)
