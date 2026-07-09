"""Tests for the comprehensive data-freshness monitor (app/monitoring/freshness.py).

Covers the OK / STALE / MISSING grading with an injected ``now`` (so the budget
is exercised deterministically), the movies + event probes against the session
DB, and — the P6 acceptance criterion — that a staleness alert *demonstrably
fires*: a stale feed grades STALE and the CLI returns a non-zero exit code.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Event, MovieShowtime
from app.monitoring import freshness as fr
from scripts import data_freshness_monitor as mon

# ---------------------------------------------------------------------------
# to_naive_utc
# ---------------------------------------------------------------------------


def test_to_naive_utc_converts_aware_to_utc() -> None:
    aware = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    out = fr.to_naive_utc(aware)
    assert out == datetime(2026, 6, 1, 12, 0, 0)
    assert out is not None and out.tzinfo is None


def test_to_naive_utc_none() -> None:
    assert fr.to_naive_utc(None) is None


# ---------------------------------------------------------------------------
# evaluate() grading with synthetic probes (pure, no DB)
# ---------------------------------------------------------------------------


def _check(key: str, *, freshest: datetime | None, max_age_hours: float = 24.0) -> fr.FeedCheck:
    return fr.FeedCheck(
        label=f"Test {key}",
        key=key,
        cadence="test",
        max_age_hours=max_age_hours,
        probe=lambda _db: freshest,
    )


def test_evaluate_ok_when_fresh() -> None:
    now = datetime(2026, 6, 10, 12, 0, 0)
    chk = _check("fresh", freshest=datetime(2026, 6, 10, 6, 0, 0))  # 6h ago
    with SessionLocal() as db:
        results = fr.evaluate(db, [chk], now=now)
    assert results[0].status == "OK"
    assert results[0].ok is True


def test_evaluate_stale_when_past_budget() -> None:
    now = datetime(2026, 6, 10, 12, 0, 0)
    chk = _check("rotten", freshest=datetime(2026, 6, 1, 12, 0, 0), max_age_hours=24.0)
    with SessionLocal() as db:
        results = fr.evaluate(db, [chk], now=now)
    assert results[0].status == "STALE"
    assert results[0].ok is False


def test_evaluate_missing_when_probe_returns_none() -> None:
    now = datetime(2026, 6, 10, 12, 0, 0)
    chk = _check("absent", freshest=None)
    with SessionLocal() as db:
        results = fr.evaluate(db, [chk], now=now)
    assert results[0].status == "MISSING"
    assert results[0].freshest is None
    assert results[0].age_hours is None


def test_default_feed_checks_cover_gas_and_movies() -> None:
    """The P0 date-desync feeds (gas, movies) must be in the default guard."""
    keys = {c.key for c in fr.FEED_CHECKS}
    assert "gas_prices_lhc" in keys
    assert "movie_showtimes" in keys
    assert {"river_scene_import", "go_lake_havasu"} <= keys


# ---------------------------------------------------------------------------
# probes against the session DB
# ---------------------------------------------------------------------------


def test_movies_probe_returns_freshest_scrape() -> None:
    suf = uuid.uuid4().hex[:8]
    src = f"test-mov-{suf}"
    try:
        with SessionLocal() as db:
            db.add(
                MovieShowtime(
                    source=src,
                    source_stable_id=f"{suf}-1",
                    theater_slug="t",
                    theater_name="T",
                    film_title="Probe",
                    show_date=date(2026, 6, 10),
                    show_time=time(19, 0),
                    scraped_at=datetime(2026, 6, 9, 8, 0, 0, tzinfo=UTC),
                )
            )
            db.commit()
        with SessionLocal() as db:
            freshest = fr._movies_probe(db)
        assert freshest is not None
        # At least as fresh as the row we inserted (other test rows may be newer).
        assert freshest >= datetime(2026, 6, 9, 8, 0, 0)
    finally:
        with SessionLocal() as db:
            db.execute(delete(MovieShowtime).where(MovieShowtime.source == src))
            db.commit()


def test_event_source_probe_picks_latest() -> None:
    src = f"test-fresh-{uuid.uuid4().hex[:8]}"
    try:
        with SessionLocal() as db:
            for d in (datetime(2026, 6, 1, 8, 0, 0), datetime(2026, 6, 5, 9, 0, 0)):
                sfx = uuid.uuid4().hex[:6]
                db.add(
                    Event(
                        title=f"Probe {sfx}",
                        normalized_title=f"probe {sfx}",
                        date=date(2026, 6, 6),
                        start_time=time(18, 0),
                        location_name="V",
                        location_normalized="v",
                        description="probe",
                        source=src,
                        created_at=d,
                    )
                )
            db.commit()
        with SessionLocal() as db:
            freshest = fr._event_source_probe(src)(db)
        assert freshest == datetime(2026, 6, 5, 9, 0, 0)
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.source == src))
            db.commit()


# ---------------------------------------------------------------------------
# the alert demonstrably fires: CLI returns non-zero on a stale feed
# ---------------------------------------------------------------------------


def test_cli_exits_nonzero_when_a_feed_is_stale(monkeypatch, capsys) -> None:
    stale = fr.FeedStatus(
        label="Gas prices",
        key="gas_prices_lhc",
        status="STALE",
        freshest=datetime(2026, 6, 1, 0, 0, 0),
        age_hours=264.0,  # 11 days — the exact P0 symptom
        max_age_hours=24.0,
    )
    monkeypatch.setattr(mon, "run", lambda now=None: [stale])
    rc = mon.main([])
    assert rc == 1
    out = capsys.readouterr().out
    assert "STALE" in out


def test_cli_exits_zero_when_all_fresh(monkeypatch) -> None:
    fresh = fr.FeedStatus(
        label="Gas prices",
        key="gas_prices_lhc",
        status="OK",
        freshest=datetime(2026, 6, 10, 0, 0, 0),
        age_hours=2.0,
        max_age_hours=24.0,
    )
    monkeypatch.setattr(mon, "run", lambda now=None: [fresh])
    assert mon.main([]) == 0
