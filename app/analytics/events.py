"""``record_event`` — single-INSERT writer for the analytics_events table.

Mirrors the v52 atomic-UPDATE pattern in ``app/home/router.py:sponsor_click``
(single SQL statement, immediate ``commit``). Wrapped in try/except so a DB
failure here never breaks the request that emitted the event — analytics
must degrade silently.

Helper is sync because every caller already holds a ``Session`` for the
request (home/router.py, sponsor_store.py) or opens its own
``SessionLocal()`` (component_builders.py — same pattern tier2_handler.py
uses at line 488 for the tier2 cache).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.db.models import AnalyticsEvent

logger = logging.getLogger(__name__)


def record_event(
    db: Session,
    event_name: str,
    *,
    slot: str | None = None,
    sponsor_id: str | None = None,
    provider_id: str | None = None,
    ranking_score: int | None = None,
    slot_origin: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Insert one ``analytics_events`` row. Best-effort — never raises.

    Single INSERT + commit per call. Analytics is per-render so volume can
    spike with traffic; the INSERT is intentionally lean (no SELECT, no
    upsert).

    On DB failure (connection blip, FK violation from a deleted sponsor,
    schema drift before the migration lands) the exception is logged at
    WARNING and swallowed. The contract with callers is "fire and forget":
    a request that emits an event must not crash because the event
    couldn't be written.
    """
    try:
        db.execute(
            insert(AnalyticsEvent).values(
                id=str(uuid4()),
                event_name=event_name,
                slot=slot,
                sponsor_id=sponsor_id,
                provider_id=provider_id,
                ranking_score=ranking_score,
                slot_origin=slot_origin,
                payload_json=payload,
            )
        )
        db.commit()
    except Exception:
        # Swallow — analytics must never break the request. ``exc_info=True``
        # so the stack still lands in logs / Sentry for investigation.
        logger.warning(
            "analytics.record_event failed (event_name=%s)",
            event_name,
            exc_info=True,
        )
        try:
            db.rollback()
        except Exception:
            # Session is already toast; nothing useful to do here.
            pass
