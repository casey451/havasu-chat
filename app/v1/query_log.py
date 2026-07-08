"""Append-only query_log writes (master spec §3.7, §4.2)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import QueryLog
from app.v1.categories import bucket_for_legacy_category

logger = logging.getLogger(__name__)

# Raw rows older than this are truncated by the retention job (plan §2.3:
# "12-month raw-row retention truncation; keep aggregates"). The query_log is
# already anonymized (no IP/UA/user-id), so retention is about not hoarding raw
# rows, not PII — aggregates a dashboard already computed survive in screenshots
# / any future rollup table.
RETENTION_DAYS = 365


def purge_old_query_logs(
    db: Session, *, older_than_days: int = RETENTION_DAYS, dry_run: bool = True
) -> int:
    """Delete (or, when ``dry_run``, just count) query_log rows older than the
    retention window. Returns the number of rows matched/deleted.

    Prod use follows CLAUDE.md: dry-run → show the count → Casey approves → run
    with ``dry_run=False``. Defaults to dry-run so an accidental call is read-only.
    """
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=older_than_days)
    matched = int(
        db.execute(
            select(func.count()).select_from(QueryLog).where(QueryLog.created_at < cutoff)
        ).scalar()
        or 0
    )
    if dry_run or matched == 0:
        return matched
    db.execute(delete(QueryLog).where(QueryLog.created_at < cutoff))
    db.commit()
    return matched


def _result_count_from_component(component_type: str, component_data: dict[str, Any]) -> int:
    if not component_data:
        return 0
    if component_type == "day_agenda":
        events = component_data.get("events") or []
        return len(events) if isinstance(events, list) else 0
    if component_type == "week_strip":
        days = component_data.get("days") or []
        return len(days) if isinstance(days, list) else 0
    if component_type in ("card_row", "business_list"):
        items = component_data.get("cards") or component_data.get("businesses") or []
        return len(items) if isinstance(items, list) else 0
    if component_type in ("single_card", "single_business_card"):
        return 1
    return 0


def log_query_intent(
    db: Session,
    *,
    normalized_intent: str | None,
    sub_intent: str | None,
    mode: str,
    category_hint: str | None = None,
    component_type: str = "none",
    component_data: dict[str, Any] | None = None,
    min_layer: str | None = None,
    result_count: int | None = None,
) -> None:
    """Best-effort insert; never raises.

    ``result_count`` overrides the component-derived count when the caller
    already knows how many results it rendered (e.g. the ``/search`` SERP, whose
    result set is a flat provider/event/category list rather than a chat
    component). ``result_count == 0`` rows are the coverage backlog the admin
    demand dashboard (``app.admin.demand``) surfaces as the acquisition list.
    """
    intent = (normalized_intent or sub_intent or mode or "unknown").strip()[:128]
    if not intent:
        intent = "unknown"
    category = bucket_for_legacy_category(category_hint) if category_hint else None
    if category is None and sub_intent:
        category = bucket_for_legacy_category(sub_intent)
    if result_count is not None:
        count = max(int(result_count), 0)
    else:
        count = _result_count_from_component(
            component_type or "none",
            component_data or {},
        )
    try:
        row = QueryLog(
            normalized_intent=intent,
            category=category,
            result_count=count,
            # Phase 2 Slice 1 telemetry (both nullable).
            min_layer=(min_layer or None),
            sub_intent=(sub_intent.strip()[:64] if sub_intent else None),
        )
        db.add(row)
        db.commit()
    except Exception:
        logger.exception("query_log_insert_failed")
        try:
            db.rollback()
        except Exception:
            pass
