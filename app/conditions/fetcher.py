"""Orchestrate per-source external conditions fetches (Phase 8a)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.conditions import airnow, nws, usgs
from app.conditions.cache import record_fetch_failure, should_skip_fetch, upsert_source
from app.conditions.constants import (
    SOURCE_AIRNOW,
    SOURCE_KEYS,
    SOURCE_NWS_ALERTS,
    SOURCE_NWS_CURRENT,
    SOURCE_NWS_FORECAST,
    SOURCE_NWS_SUNSET,
    SOURCE_USGS,
    TTL_BY_SOURCE,
)
from app.core.background import with_retry
from app.db.models import ExternalConditionsCache

logger = logging.getLogger(__name__)

_FETCHERS: dict[str, Callable[[], dict[str, Any]]] = {
    SOURCE_AIRNOW: airnow.fetch_airnow_current,
    SOURCE_NWS_ALERTS: nws.fetch_nws_alerts_lhc_zone,
    SOURCE_NWS_CURRENT: nws.fetch_nws_current,
    SOURCE_NWS_FORECAST: nws.fetch_nws_forecast_daily,
    SOURCE_NWS_SUNSET: nws.fetch_nws_sunset,
    SOURCE_USGS: usgs.fetch_usgs_lake_havasu,
}


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def fetch_one_source(
    db: Session,
    source: str,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> bool:
    """Fetch and upsert one source. Returns True on success.

    Phase 8a.3: pass ``force=True`` to bypass the circuit-breaker gate
    (see ``cache.should_skip_fetch``). Useful after deploying an API-rename
    fix to unmask the next fetch attempt without waiting for the cooldown.
    """
    now = now or _utc_now()
    if source not in _FETCHERS:
        raise ValueError(f"unknown conditions source: {source}")

    row = db.get(ExternalConditionsCache, source)
    if not force and should_skip_fetch(row, now=now):
        logger.info("conditions.circuit_skipped", extra={"source": source})
        return False

    fn = _FETCHERS[source]

    def _run() -> dict[str, Any]:
        return fn()

    try:
        data = with_retry(
            _run,
            max_attempts=3,
            backoff_initial_s=1.0,
            backoff_multiplier=2.0,
        )
        if data is None:
            raise RuntimeError(f"fetch exhausted for {source}")
        upsert_source(
            db,
            source,
            data,
            ttl_seconds=TTL_BY_SOURCE.get(source),
            success=True,
            now=now,
        )
        logger.info("conditions.fetch_succeeded", extra={"source": source})
        return True
    except Exception as exc:
        logger.exception("conditions.fetch_failed", extra={"source": source})
        record_fetch_failure(db, source, str(exc), now=now)
        return False


def fetch_sources(
    db: Session,
    sources: list[str],
    *,
    force: bool = False,
) -> dict[str, bool]:
    results: dict[str, bool] = {}
    for source in sources:
        try:
            results[source] = fetch_one_source(db, source, force=force)
        except Exception:
            logger.exception("conditions.fetch_failed", extra={"source": source})
            results[source] = False
    return results


def all_source_keys() -> tuple[str, ...]:
    return SOURCE_KEYS
