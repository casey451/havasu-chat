"""Event card view-model hooks (Phase 9a)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.providers import queries as provider_queries
from app.providers.view_models import HavaCardViewModel


def build_card_view_model_for_event_occurrence(
    db: Session,
    event_id: str,
    occurrence_date: date,
    *,
    now: Optional[datetime] = None,
) -> HavaCardViewModel | None:
    """Delegate to provider queries occurrence-aware card builder."""
    return provider_queries.build_card_view_model_for_event_occurrence(
        db, event_id, occurrence_date, now=now
    )
