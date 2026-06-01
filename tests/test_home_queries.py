"""Tests for ``app.home.queries``."""

from __future__ import annotations

import importlib.util
import sys
import uuid
from datetime import date, datetime, time
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Query, Session, sessionmaker

from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import Base, SessionLocal
from app.db.models import Event, Provider
from app.home import queries as home_queries
from app.home.queries import _format_phone

# --- Fix #3 (placeholder phones) ---


def test_format_phone_strips_placeholder_nanp() -> None:
    assert _format_phone("(928) 555-0100") == (None, None)


def test_format_phone_strips_placeholder_other_areacode() -> None:
    assert _format_phone("(212) 555-0199") == (None, None)


def test_format_phone_keeps_real_number() -> None:
    assert _format_phone("(928) 855-1234") == ("(928) 855-1234", "9288551234")


def test_format_phone_keeps_real_555_outside_01xx() -> None:
    assert _format_phone("(928) 555-1234") == ("(928) 555-1234", "9285551234")


def test_format_phone_handles_already_digits() -> None:
    assert _format_phone("9285550100") == (None, None)


@pytest.fixture(scope="module")
def placeholder_cleanup_mod():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "cleanup" / "null_placeholder_phones.py"
    name = "null_placeholder_phones_test_mod"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Script mutates sys.path — mirror normal execution
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = S()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _seed_three_placeholder_two_real(db) -> None:
    suf = uuid.uuid4().hex[:8]
    rows = [
        Provider(
            provider_name=f"Placeholder A {suf}",
            category="retail",
            phone="(928) 555-0100",
            verified=True,
            draft=False,
            is_active=True,
            source="test-home-queries",
        ),
        Provider(
            provider_name=f"Placeholder B {suf}",
            category="retail",
            phone="(212) 555-0199",
            verified=True,
            draft=False,
            is_active=True,
            source="test-home-queries",
        ),
        Provider(
            provider_name=f"Placeholder C {suf}",
            category="retail",
            phone="9285550100",
            verified=True,
            draft=False,
            is_active=True,
            source="test-home-queries",
        ),
        Provider(
            provider_name=f"Real A {suf}",
            category="retail",
            phone="(928) 855-1234",
            verified=True,
            draft=False,
            is_active=True,
            source="test-home-queries",
        ),
        Provider(
            provider_name=f"Real B {suf}",
            category="retail",
            phone="(928) 555-1234",
            verified=True,
            draft=False,
            is_active=True,
            source="test-home-queries",
        ),
    ]
    db.add_all(rows)
    db.commit()


def test_cleanup_script_dry_run(placeholder_cleanup_mod, db_session, tmp_path: Path) -> None:
    _seed_three_placeholder_two_real(db_session)
    result = placeholder_cleanup_mod.run_placeholder_cleanup(
        db_session, apply=False, log_dir=tmp_path
    )
    assert result.matched == 3
    assert result.updated == 0
    assert result.log_path.is_file()
    assert db_session.query(Provider).filter(Provider.phone.isnot(None)).count() == 5


def test_cleanup_script_apply_idempotent(
    placeholder_cleanup_mod, db_session, tmp_path: Path
) -> None:
    _seed_three_placeholder_two_real(db_session)
    r1 = placeholder_cleanup_mod.run_placeholder_cleanup(db_session, apply=True, log_dir=tmp_path)
    assert r1.matched == 3
    assert r1.updated == 3

    r2 = placeholder_cleanup_mod.run_placeholder_cleanup(db_session, apply=True, log_dir=tmp_path)
    assert r2.matched == 0
    assert r2.updated == 0

    remaining_with_phone = db_session.query(Provider).filter(Provider.phone.isnot(None)).count()
    assert remaining_with_phone == 2


# --- Fix #1 (tonight) ---


@pytest.fixture
def tonight_db():
    """Session bound to the test SQLite DB used by the Tonight tests."""
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture()
def _wipe_events(tonight_db: Session):
    """Reset the events table before/after each Tonight test."""
    tonight_db.query(Event).delete()
    tonight_db.commit()
    yield
    tonight_db.query(Event).delete()
    tonight_db.commit()


def _fix_now(
    monkeypatch: pytest.MonkeyPatch,
    hour: int,
    minute: int = 0,
    *,
    on_date: date | None = None,
) -> datetime:
    """Pin ``home_queries.now_lake_havasu`` to ``on_date`` at ``hour:minute``."""
    today = on_date or datetime.now(LAKE_HAVASU_TZ).date()
    fixed = datetime(today.year, today.month, today.day, hour, minute, tzinfo=LAKE_HAVASU_TZ)
    monkeypatch.setattr(home_queries, "now_lake_havasu", lambda: fixed)
    return fixed


def _make_event(
    db: Session,
    *,
    title: str | None = None,
    start: time = time(10, 0),
    location_name: str = "Aquatic Center",
    on_date: date | None = None,
    featured: bool = False,
) -> Event:
    on_date = on_date or datetime.now(LAKE_HAVASU_TZ).date()
    title = title or f"Event {uuid.uuid4().hex[:8]}"
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on_date,
        start_time=start,
        location_name=location_name,
        location_normalized=location_name.lower(),
        description="An event",
        event_url="https://example.com/e",
        tags=[],
        status="live",
        source="test_home_queries",
        verified=True,
        featured=featured,
    )
    db.add(ev)
    db.flush()
    return ev


def test_tonight_drops_past_events(
    tonight_db: Session, _wipe_events, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At 14:00 a 05:00 lap swim should not headline the row."""
    _fix_now(monkeypatch, 14, 0)
    _make_event(tonight_db, title="Lap swim", start=time(5, 0))
    tonight_db.commit()
    rows = home_queries.tonight(tonight_db)
    assert rows == []


def test_tonight_keeps_future_events_today(
    tonight_db: Session, _wipe_events, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At 14:00 a 19:00 concert is still ahead — keep it."""
    _fix_now(monkeypatch, 14, 0)
    _make_event(tonight_db, title="Concert", start=time(19, 0))
    tonight_db.commit()
    rows = home_queries.tonight(tonight_db)
    assert len(rows) == 1
    assert rows[0]["name"] == "Concert"


def test_tonight_label_today_before_4pm(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed = _fix_now(monkeypatch, 14, 0)
    assert home_queries.tonight_or_today_label(fixed) == "Today"


def test_tonight_label_tonight_after_4pm(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed = _fix_now(monkeypatch, 17, 0)
    assert home_queries.tonight_or_today_label(fixed) == "Tonight"


def test_tonight_floor_applies_4pm_after_4pm(
    tonight_db: Session, _wipe_events, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At 17:00, a 12:00 event is in the past for the evening band — drop it."""
    _fix_now(monkeypatch, 17, 0)
    _make_event(tonight_db, title="Lunch lecture", start=time(12, 0))
    tonight_db.commit()
    rows = home_queries.tonight(tonight_db)
    assert rows == []


def test_tonight_includes_all_day_events(
    tonight_db: Session, _wipe_events, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The filter has an ``OR(start_time IS NULL)`` branch so all-day events surface.

    The current schema sets ``events.start_time NOT NULL`` so a literal
    ``None`` row can't be inserted; verify the SQL contract instead so a
    future migration that relaxes the column is already supported.
    """
    _fix_now(monkeypatch, 14, 0)
    captured: list[str] = []
    real_all = Query.all

    def spy(self):
        captured.append(str(self.statement.compile(compile_kwargs={"literal_binds": True})))
        return real_all(self)

    monkeypatch.setattr(Query, "all", spy)
    home_queries.tonight(tonight_db)
    assert any("start_time IS NULL" in sql for sql in captured), (
        "tonight() filter should permit start_time=None for all-day events; "
        f"captured SQL: {captured}"
    )


def test_tonight_venue_diversity(
    tonight_db: Session, _wipe_events, monkeypatch: pytest.MonkeyPatch
) -> None:
    """3 Aquatic + 2 other venues with limit=3 → 1 Aquatic + 2 others."""
    _fix_now(monkeypatch, 9, 0)
    for hour in (10, 11, 12):
        _make_event(
            tonight_db,
            title=f"Aquatic {hour}",
            start=time(hour, 0),
            location_name="Aquatic Center",
        )
    _make_event(
        tonight_db,
        title="Library event",
        start=time(13, 0),
        location_name="Mohave Library",
    )
    _make_event(
        tonight_db,
        title="Park event",
        start=time(14, 0),
        location_name="Rotary Park",
    )
    tonight_db.commit()
    rows = home_queries.tonight(tonight_db, limit=3)
    locations = [r["footer_text"] for r in rows]
    assert len(rows) == 3
    assert sum(1 for loc in locations if loc == "Aquatic Center") == 1, locations
    assert "Mohave Library" in locations
    assert "Rotary Park" in locations


def test_tonight_diversity_backfill_when_single_venue(
    tonight_db: Session, _wipe_events, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When only one venue has events today, backfill rather than under-fill."""
    _fix_now(monkeypatch, 9, 0)
    for hour in (10, 11, 12, 13, 14):
        _make_event(
            tonight_db,
            title=f"Aquatic {hour}",
            start=time(hour, 0),
            location_name="Aquatic Center",
        )
    tonight_db.commit()
    rows = home_queries.tonight(tonight_db, limit=3)
    assert len(rows) == 3
    assert all(r["footer_text"] == "Aquatic Center" for r in rows)
