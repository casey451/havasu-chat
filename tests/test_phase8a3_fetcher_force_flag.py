"""Phase 8a.3 — fetch_one_source / fetch_sources honor a `force=True` bypass
of the circuit-breaker gate (`cache.should_skip_fetch`).

Two tests pin the new keyword-only flag at the orchestrator layer:

1. Default behavior (`force=False`): when `next_attempt_after` is in the
   future, `fetch_one_source` short-circuits with `return False` BEFORE
   invoking the source-level fetcher. This is the pre-Phase-8a.3 behavior.
2. `force=True`: the same row state is ignored — the source fetcher IS
   called and `fetch_one_source` returns True on success.

The tests monkeypatch ``fetcher._FETCHERS`` to insert a call-counting spy
in place of the real ``usgs.fetch_usgs_lake_havasu``; no network is touched.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.conditions import fetcher
from app.conditions.constants import SOURCE_USGS
from app.db.database import SessionLocal
from app.db.models import ExternalConditionsCache

_FIXED_NOW = datetime(2026, 5, 21, 22, 0, 0)
_FUTURE = _FIXED_NOW + timedelta(hours=6)


@pytest.fixture
def cache_row_with_active_breaker():
    """Seed external_conditions_cache with a usgs row whose breaker is active.

    Mirrors the prod state observed before Phase 8a.3: error_count >= 3
    triggers next_attempt_after = now + hours; the gate then refuses
    every cron tick until cooldown lapses.
    """
    with SessionLocal() as db:
        existing = db.get(ExternalConditionsCache, SOURCE_USGS)
        if existing is not None:
            db.delete(existing)
            db.commit()
        row = ExternalConditionsCache(
            source=SOURCE_USGS,
            fetched_at=_FIXED_NOW - timedelta(hours=4),
            data={"lake_gauge_ft": 48.79, "lake_storage_acft": 584800.0},
            ttl_seconds=3600,
            last_error="fetch exhausted for usgs_09427500",
            error_count=5,
            last_attempt_at=_FIXED_NOW - timedelta(minutes=30),
            next_attempt_after=_FUTURE,
        )
        db.add(row)
        db.commit()
    yield
    with SessionLocal() as db:
        existing = db.get(ExternalConditionsCache, SOURCE_USGS)
        if existing is not None:
            db.delete(existing)
            db.commit()


def test_fetch_one_source_default_respects_active_breaker(
    cache_row_with_active_breaker: None,
) -> None:
    """Without force, fetch_one_source skips when next_attempt_after > now."""
    call_count = 0

    def _spy() -> dict:
        nonlocal call_count
        call_count += 1
        return {"lake_gauge_ft": 49.13, "lake_storage_acft": 591300.0}

    with patch.dict(fetcher._FETCHERS, {SOURCE_USGS: _spy}, clear=False):
        with SessionLocal() as db:
            result = fetcher.fetch_one_source(db, SOURCE_USGS, now=_FIXED_NOW)

    assert result is False, "default should return False when breaker is active"
    assert call_count == 0, "source fetcher must NOT be called when breaker skips"


def test_fetch_one_source_with_force_bypasses_active_breaker(
    cache_row_with_active_breaker: None,
) -> None:
    """With force=True, fetch_one_source ignores should_skip_fetch and runs the fetcher."""
    call_count = 0

    def _spy() -> dict:
        nonlocal call_count
        call_count += 1
        return {"lake_gauge_ft": 49.13, "lake_storage_acft": 591300.0}

    with patch.dict(fetcher._FETCHERS, {SOURCE_USGS: _spy}, clear=False):
        with SessionLocal() as db:
            result = fetcher.fetch_one_source(
                db, SOURCE_USGS, now=_FIXED_NOW, force=True,
            )

    assert result is True, "force=True must bypass breaker and complete fetch"
    assert call_count == 1, "source fetcher must be called exactly once when force=True"
