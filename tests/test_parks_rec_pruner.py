"""Tests for ``app.contrib.parks_rec_loader.prune_stale_aquatic`` and the
``scripts/parks_rec_prune.py`` CLI surface.

The pruner hard-deletes Event rows whose ``source_url`` matches the
aquatic schedule URL substring AND whose ``date`` falls before
``today - grace_days``. Everything else stays put — WebTrac
registrations, admin events, river-scene imports, and recent aquatic
slots inside the grace window.

In-memory SQLite only; no real DB or HTTP access.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date, time, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.contrib.parks_rec_loader import (
    AQUATIC_PRUNE_GRACE_DAYS,
    AQUATIC_SCHEDULE_URL,
    AQUATIC_SOURCE,
    prune_stale_aquatic,
)
from app.db.database import Base
from app.db.models import Event

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


def _aquatic_url(slot_date: date, slug: str = "lap-swim", hhmm: str = "06-00") -> str:
    return f"{AQUATIC_SCHEDULE_URL}#{slot_date.isoformat()}|{slug}|{hhmm}"


def _make_event(
    *,
    eid: str,
    when: date,
    source_url: str | None,
    source: str = "admin",
    title: str | None = None,
) -> Event:
    return Event(
        id=eid,
        title=title or eid,
        normalized_title=(title or eid).lower(),
        date=when,
        end_date=None,
        start_time=time(6, 0),
        end_time=time(7, 0),
        location_name="Aquatic Center",
        location_normalized="aquatic center",
        description="seed",
        event_url=AQUATIC_SCHEDULE_URL,
        source_url=source_url,
        source=source,
    )


@pytest.fixture()
def seeded(db_session):
    """Seed a representative spread of Event rows.

    Categorized so each test can assert on which rows survived a prune.
    """
    today = date(2026, 5, 8)  # frozen "today" for deterministic cutoff math

    # cutoff = today - 7 = 2026-05-01. Anything STRICTLY before 2026-05-01 is stale.

    rows = {
        # Aquatic, well past cutoff — should prune
        "aq_old_1": _make_event(
            eid="aq_old_1",
            when=today - timedelta(days=30),
            source_url=_aquatic_url(today - timedelta(days=30), "aqua-aerobics", "06-00"),
            title="Aqua Aerobics (old)",
        ),
        "aq_old_2": _make_event(
            eid="aq_old_2",
            when=today - timedelta(days=8),  # one day past cutoff
            source_url=_aquatic_url(today - timedelta(days=8), "lap-swim", "07-00"),
            title="Lap Swim (old)",
        ),
        # Aquatic, exactly on cutoff date — kept (predicate is < cutoff)
        "aq_boundary": _make_event(
            eid="aq_boundary",
            when=today - timedelta(days=7),
            source_url=_aquatic_url(today - timedelta(days=7), "lap-swim", "08-00"),
            title="Lap Swim (boundary)",
        ),
        # Aquatic, fresh (within grace) — kept
        "aq_fresh": _make_event(
            eid="aq_fresh",
            when=today - timedelta(days=2),
            source_url=_aquatic_url(today - timedelta(days=2), "lap-swim", "09-00"),
            title="Lap Swim (fresh)",
        ),
        # Aquatic, future — kept
        "aq_future": _make_event(
            eid="aq_future",
            when=today + timedelta(days=3),
            source_url=_aquatic_url(today + timedelta(days=3), "lap-swim", "06-00"),
            title="Lap Swim (future)",
        ),
        # WebTrac, very old — kept (different host pattern)
        "wt_old": _make_event(
            eid="wt_old",
            when=today - timedelta(days=60),
            source_url="https://register.lhcaz.gov/webtrac/web/iteminfo.html?fmid=12345",
            title="WebTrac old class",
        ),
        # Admin event with no source_url, very old — kept
        "admin_old": _make_event(
            eid="admin_old",
            when=today - timedelta(days=60),
            source_url=None,
            title="Admin old fair",
        ),
        # River-scene, very old — kept (different host pattern)
        "rs_old": _make_event(
            eid="rs_old",
            when=today - timedelta(days=60),
            source_url="https://riverscenemagazine.com/event/old",
            source="river_scene_import",
            title="RS old",
        ),
    }

    db_session.add_all(rows.values())
    db_session.commit()
    return today, rows


# ---------------------------------------------------------------------------
# prune_stale_aquatic — behavior
# ---------------------------------------------------------------------------


def test_prune_deletes_only_stale_aquatic(db_session, seeded):
    today, rows = seeded

    stats = prune_stale_aquatic(db=db_session, today=today)

    assert stats.source == AQUATIC_SOURCE
    assert stats.cutoff == today - timedelta(days=AQUATIC_PRUNE_GRACE_DAYS)
    assert stats.matched == 2  # aq_old_1, aq_old_2
    assert stats.deleted == 2
    assert stats.dry_run is False
    assert stats.errors == []

    surviving_ids = {e.id for e in db_session.query(Event).all()}
    expected_survivors = {
        "aq_boundary",
        "aq_fresh",
        "aq_future",
        "wt_old",
        "admin_old",
        "rs_old",
    }
    assert surviving_ids == expected_survivors


def test_prune_dry_run_leaves_db_intact(db_session, seeded):
    today, rows = seeded
    before = {e.id for e in db_session.query(Event).all()}

    stats = prune_stale_aquatic(db=db_session, today=today, dry_run=True)

    assert stats.matched == 2
    assert stats.deleted == 0
    assert stats.dry_run is True

    after = {e.id for e in db_session.query(Event).all()}
    assert after == before


def test_prune_no_matches_is_noop(db_session):
    """Empty DB → 0 matched, 0 deleted, no errors."""
    stats = prune_stale_aquatic(db=db_session, today=date(2026, 5, 8))
    assert stats.matched == 0
    assert stats.deleted == 0
    assert stats.errors == []


def test_prune_custom_grace_days(db_session, seeded):
    """grace_days=0 → cutoff is today; aq_fresh (2 days back) becomes prunable."""
    today, _rows = seeded

    stats = prune_stale_aquatic(db=db_session, today=today, grace_days=0)

    assert stats.cutoff == today
    # aq_old_1, aq_old_2, aq_boundary (-7), aq_fresh (-2) all stale; aq_future kept
    assert stats.matched == 4
    assert stats.deleted == 4

    surviving_aquatic = (
        db_session.query(Event)
        .filter(Event.source_url.like(f"%{AQUATIC_SCHEDULE_URL.split('//')[1]}%"))
        .all()
    )
    assert {e.id for e in surviving_aquatic} == {"aq_future"}


def test_prune_negative_grace_days_clamped_to_zero(db_session, seeded):
    """Defensive: a caller passing -5 should get the same behavior as 0."""
    today, _rows = seeded
    stats = prune_stale_aquatic(db=db_session, today=today, grace_days=-5)
    assert stats.cutoff == today  # clamped


def test_prune_default_today_is_real_today(db_session):
    """When today=None the function uses ``date.today()``. Smoke-only:
    verify cutoff equals today's-real-today minus the grace days."""
    stats = prune_stale_aquatic(db=db_session)
    assert stats.cutoff == date.today() - timedelta(days=AQUATIC_PRUNE_GRACE_DAYS)


def test_prune_does_not_touch_webtrac_or_admin(db_session, seeded):
    """Belt-and-suspenders: even with grace_days=0 (most aggressive),
    non-aquatic source_urls survive."""
    today, _rows = seeded
    prune_stale_aquatic(db=db_session, today=today, grace_days=0)

    ids = {e.id for e in db_session.query(Event).all()}
    assert "wt_old" in ids
    assert "admin_old" in ids
    assert "rs_old" in ids


# ---------------------------------------------------------------------------
# CLI module — sanity check that it imports and exposes main()
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def prune_cli_mod():
    path = ROOT / "scripts" / "parks_rec_prune.py"
    name = "parks_rec_prune_test_mod"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_cli_module_imports_and_exposes_main(prune_cli_mod):
    assert callable(prune_cli_mod.main)
