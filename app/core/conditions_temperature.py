"""Live temperature read for ranking + chat (Phase 8a)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.conditions.constants import SOURCE_NWS_CURRENT
from app.core.ranking import STUB_CURRENT_TEMPERATURE_F

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def read_current_temperature_f(db: Session) -> float:
    """Read NWS current temp from cache; fall back to stub when missing/stale."""
    from app.conditions.cache import read_source

    row = read_source(db, SOURCE_NWS_CURRENT)
    if row is None or row.is_stale:
        if row is None:
            logger.debug("conditions.fallback_to_stub", extra={"reason": "missing"})
        else:
            logger.debug("conditions.fallback_to_stub", extra={"reason": "stale"})
        return STUB_CURRENT_TEMPERATURE_F
    temp = row.data.get("temperature_f")
    if temp is None:
        logger.debug("conditions.fallback_to_stub", extra={"reason": "no_temp"})
        return STUB_CURRENT_TEMPERATURE_F
    try:
        return float(temp)
    except (TypeError, ValueError):
        return STUB_CURRENT_TEMPERATURE_F
