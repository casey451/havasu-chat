"""Read/write external_conditions_cache with in-process wrap (Phase 8a)."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.conditions.constants import TTL_BY_SOURCE
from app.db.models import ExternalConditionsCache

logger = logging.getLogger(__name__)

_LOCAL_TTL_SECONDS = 300
_local_lock = threading.Lock()
_local_cache: dict[str, tuple[datetime, dict, datetime, int, bool]] = {}


@dataclass(frozen=True)
class CacheReadResult:
    data: dict
    fetched_at: datetime
    ttl_seconds: int
    is_stale: bool


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _is_stale(fetched_at: datetime, ttl_seconds: int, now: datetime) -> bool:
    return (now - fetched_at).total_seconds() > ttl_seconds


def read_source(db: Session, source: str, *, now: datetime | None = None) -> CacheReadResult | None:
    """Return cached payload or None if missing."""
    now = now or _utc_now()
    with _local_lock:
        cached = _local_cache.get(source)
        if cached is not None:
            cached_at, data, fetched_at, ttl_seconds, is_stale = cached
            if (now - cached_at).total_seconds() < _LOCAL_TTL_SECONDS:
                return CacheReadResult(
                    data=data,
                    fetched_at=fetched_at,
                    ttl_seconds=ttl_seconds,
                    is_stale=is_stale,
                )

    row = db.get(ExternalConditionsCache, source)
    if row is None:
        return None

    data = row.data if isinstance(row.data, dict) else {}
    ttl = row.ttl_seconds or TTL_BY_SOURCE.get(source, 1800)
    stale = _is_stale(row.fetched_at, ttl, now)
    result = CacheReadResult(
        data=data,
        fetched_at=row.fetched_at,
        ttl_seconds=ttl,
        is_stale=stale,
    )
    with _local_lock:
        _local_cache[source] = (now, data, row.fetched_at, ttl, stale)
    return result


def invalidate_local_cache(source: str | None = None) -> None:
    with _local_lock:
        if source is None:
            _local_cache.clear()
        else:
            _local_cache.pop(source, None)


def should_skip_fetch(row: ExternalConditionsCache | None, *, now: datetime) -> bool:
    if row is None or row.next_attempt_after is None:
        return False
    return now < row.next_attempt_after


def upsert_source(
    db: Session,
    source: str,
    data: dict,
    *,
    ttl_seconds: int | None = None,
    success: bool = True,
    error_message: str | None = None,
    now: datetime | None = None,
) -> None:
    """UPSERT one cache row; update circuit-breaker fields on failure."""
    now = now or _utc_now()
    ttl = ttl_seconds if ttl_seconds is not None else TTL_BY_SOURCE.get(source, 1800)
    row = db.get(ExternalConditionsCache, source)
    if row is None:
        row = ExternalConditionsCache(
            source=source,
            fetched_at=now,
            data=data,
            ttl_seconds=ttl,
            last_error=None,
            error_count=0,
            last_attempt_at=now,
            next_attempt_after=None,
        )
        db.add(row)
    row.last_attempt_at = now
    if success:
        row.fetched_at = now
        row.data = data
        row.ttl_seconds = ttl
        row.last_error = None
        row.error_count = 0
        row.next_attempt_after = None
    else:
        row.last_error = (error_message or "unknown")[:500]
        row.error_count = int(row.error_count or 0) + 1
        if row.error_count >= 3:
            hours = min(row.error_count, 6)
            row.next_attempt_after = now + timedelta(hours=hours)
    invalidate_local_cache(source)
    db.flush()


def record_fetch_failure(
    db: Session, source: str, error_message: str, *, now: datetime | None = None
) -> None:
    now = now or _utc_now()
    row = db.get(ExternalConditionsCache, source)
    prior_data: dict = {}
    if row is not None and isinstance(row.data, dict):
        prior_data = row.data
    upsert_source(
        db,
        source,
        prior_data,
        success=False,
        error_message=error_message,
        now=now,
    )
