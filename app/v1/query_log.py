"""Append-only query_log writes (master spec §3.7, §4.2)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import QueryLog
from app.v1.categories import bucket_for_legacy_category

logger = logging.getLogger(__name__)


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
) -> None:
    """Best-effort insert; never raises."""
    intent = (normalized_intent or sub_intent or mode or "unknown").strip()[:128]
    if not intent:
        intent = "unknown"
    category = bucket_for_legacy_category(category_hint) if category_hint else None
    if category is None and sub_intent:
        category = bucket_for_legacy_category(sub_intent)
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
