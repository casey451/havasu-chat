"""Phase 8a — alert threshold evaluation."""

from __future__ import annotations

from datetime import UTC, datetime

from app.alerts.evaluator import (
    evaluate_aqi_alert,
    evaluate_heat_advisory,
    evaluate_lake_hazard,
)
from app.conditions.cache import upsert_source
from app.conditions.constants import SOURCE_AIRNOW, SOURCE_NWS_ALERTS, SOURCE_NWS_FORECAST
from app.db.database import SessionLocal


def test_heat_advisory_fires_on_nws_event() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        upsert_source(
            db,
            SOURCE_NWS_ALERTS,
            {"alerts": [{"event": "Excessive Heat Warning"}]},
            now=now,
        )
        result = evaluate_heat_advisory(db)
    assert result.fired is True


def test_aqi_alert_fires_above_threshold() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        upsert_source(
            db,
            SOURCE_AIRNOW,
            {"rows": [{"AQI": 160, "ParameterName": "O3"}]},
            now=now,
        )
        result = evaluate_aqi_alert(db)
    assert result.fired is True


def test_aqi_alert_suppressed_when_stale() -> None:
    old = datetime(2020, 1, 1, tzinfo=None)
    with SessionLocal() as db:
        upsert_source(
            db,
            SOURCE_AIRNOW,
            {"rows": [{"AQI": 200, "ParameterName": "O3"}]},
            now=old,
        )
        db.commit()
        result = evaluate_aqi_alert(db)
    assert result.fired is False


def test_lake_hazard_nws_keyword() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        upsert_source(
            db,
            SOURCE_NWS_ALERTS,
            {"alerts": [{"event": "Flash Flood Warning", "headline": "flood"}]},
            now=now,
        )
        result = evaluate_lake_hazard(db)
    assert result.fired is True


def test_heat_advisory_forecast_threshold() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        upsert_source(
            db,
            SOURCE_NWS_FORECAST,
            {"forecast_high_f": 115.0},
            now=now,
        )
        result = evaluate_heat_advisory(db)
    assert result.fired is True
