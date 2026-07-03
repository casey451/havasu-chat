"""Conditions cron hygiene (2026-07-01 audit).

Three fixes under test: (1) SOURCE_KEYS only lists sources the cron can
actually fetch (gas is written by its own workflow — listing it made every
15-min tick raise "unknown conditions source"); (2) a TTL freshness gate so a
source inside its TTL is not re-fetched (Open-UV's 50/day free tier was being
hit ~96x/day); (3) the never-read NWS sunset source is retired.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.conditions.constants import (
    SOURCE_GAS,
    SOURCE_KEYS,
    SOURCE_NWS_SUNSET,
    SOURCE_OPENUV,
    SOURCE_USGS,
    TTL_BY_SOURCE,
)
from app.conditions.fetcher import _FETCHERS, fetch_one_source
from app.db.database import SessionLocal
from app.db.models import ExternalConditionsCache


def test_every_cron_source_has_a_fetcher():
    # The invariant that broke: a SOURCE_KEYS entry without a _FETCHERS entry
    # raises on every cron tick.
    missing = [s for s in SOURCE_KEYS if s not in _FETCHERS]
    assert missing == []


def test_gas_and_sunset_are_not_cron_sources():
    assert SOURCE_GAS not in SOURCE_KEYS  # written by gas-prices.yml, no fetcher
    assert SOURCE_NWS_SUNSET not in SOURCE_KEYS  # retired: fetched-but-never-read
    assert SOURCE_NWS_SUNSET not in _FETCHERS
    assert not hasattr(__import__("app.conditions.nws", fromlist=["nws"]), "fetch_nws_sunset")


def _seed_row(db, source: str, fetched_at: datetime) -> None:
    row = db.get(ExternalConditionsCache, source)
    if row is None:
        row = ExternalConditionsCache(source=source, data={}, ttl_seconds=3600)
        db.add(row)
    row.fetched_at = fetched_at
    row.data = {"seeded": True}
    row.last_error = None
    row.error_count = 0
    row.next_attempt_after = None
    db.commit()


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def test_fresh_source_is_not_refetched(monkeypatch):
    calls: list[str] = []
    monkeypatch.setitem(_FETCHERS, SOURCE_USGS, lambda: calls.append("hit") or {"x": 1})
    with SessionLocal() as db:
        _seed_row(db, SOURCE_USGS, _now() - timedelta(seconds=60))  # well inside 3600s TTL
        ok = fetch_one_source(db, SOURCE_USGS, now=_now())
    assert ok is True  # fresh counts as success, not failure
    assert calls == []  # and no HTTP fetch happened


def test_stale_source_is_refetched(monkeypatch):
    calls: list[str] = []

    def fake_fetch():
        calls.append("hit")
        return {"x": 2}

    monkeypatch.setitem(_FETCHERS, SOURCE_USGS, fake_fetch)
    ttl = TTL_BY_SOURCE[SOURCE_USGS]
    with SessionLocal() as db:
        _seed_row(db, SOURCE_USGS, _now() - timedelta(seconds=ttl + 60))
        ok = fetch_one_source(db, SOURCE_USGS, now=_now())
    assert ok is True
    assert calls == ["hit"]


def test_force_bypasses_freshness_gate(monkeypatch):
    calls: list[str] = []
    monkeypatch.setitem(_FETCHERS, SOURCE_OPENUV, lambda: calls.append("hit") or {"uv": 5})
    with SessionLocal() as db:
        _seed_row(db, SOURCE_OPENUV, _now() - timedelta(seconds=30))
        ok = fetch_one_source(db, SOURCE_OPENUV, now=_now(), force=True)
    assert ok is True
    assert calls == ["hit"]


def test_failed_row_still_retries(monkeypatch):
    # fetched_at only advances on success, so a row whose last SUCCESS is old
    # keeps retrying each tick even if a recent attempt failed (circuit breaker
    # governs pacing separately).
    calls: list[str] = []
    monkeypatch.setitem(_FETCHERS, SOURCE_USGS, lambda: calls.append("hit") or {"x": 3})
    ttl = TTL_BY_SOURCE[SOURCE_USGS]
    with SessionLocal() as db:
        _seed_row(db, SOURCE_USGS, _now() - timedelta(seconds=ttl * 2))
        row = db.get(ExternalConditionsCache, SOURCE_USGS)
        row.last_error = "boom"
        row.error_count = 1  # below the >=3 circuit threshold
        db.commit()
        ok = fetch_one_source(db, SOURCE_USGS, now=_now())
    assert ok is True
    assert calls == ["hit"]


def teardown_module(module):  # noqa: ARG001
    # Leave no seeded/overwritten cache rows behind for other test files.
    from app.conditions.cache import invalidate_local_cache

    with SessionLocal() as db:
        for source in (SOURCE_USGS, SOURCE_OPENUV):
            row = db.get(ExternalConditionsCache, source)
            if row is not None:
                db.delete(row)
        db.commit()
    invalidate_local_cache()
