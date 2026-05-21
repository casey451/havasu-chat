"""Phase 8a — read_current_temperature_f stub fallback + live read."""

from __future__ import annotations

from datetime import UTC, datetime

from app.conditions.cache import upsert_source
from app.conditions.constants import SOURCE_NWS_CURRENT
from app.core.conditions_temperature import read_current_temperature_f
from app.core.ranking import STUB_CURRENT_TEMPERATURE_F
from app.db.database import SessionLocal


def test_read_current_temperature_f_uses_cache() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        upsert_source(db, SOURCE_NWS_CURRENT, {"temperature_f": 112.0}, now=now)
        db.commit()
        assert read_current_temperature_f(db) == 112.0


def test_read_current_temperature_f_falls_back_to_stub() -> None:
    from app.conditions.cache import invalidate_local_cache
    from app.conditions.constants import SOURCE_NWS_CURRENT
    from app.db.models import ExternalConditionsCache

    invalidate_local_cache()
    with SessionLocal() as db:
        row = db.get(ExternalConditionsCache, SOURCE_NWS_CURRENT)
        if row is not None:
            db.delete(row)
            db.commit()
        assert read_current_temperature_f(db) == STUB_CURRENT_TEMPERATURE_F
