"""Phase A2 -- unified safety-rule audit report (read-only)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.alerts.report import (
    STATUS_CLEAR,
    STATUS_DATA_UNAVAILABLE,
    STATUS_FIRED,
    build_safety_report,
)
from app.conditions.cache import upsert_source
from app.conditions.constants import (
    SOURCE_AIRNOW,
    SOURCE_NWS_ALERTS,
    SOURCE_NWS_CURRENT,
    SOURCE_NWS_FORECAST,
    SOURCE_USGS,
)
from app.db.database import SessionLocal
from app.db.models import AlertDispatched


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def test_report_covers_all_v1_rules() -> None:
    with SessionLocal() as db:
        report = build_safety_report(db)
    types = {r.alert_type for r in report.rules}
    assert types == {"heat_advisory", "aqi_alert", "lake_hazard"}
    assert report.dry_run is True


def test_report_marks_missing_sources_unavailable() -> None:
    # No cache rows seeded for aqi -> data_unavailable, not "clear".
    with SessionLocal() as db:
        report = build_safety_report(db, alert_type_filter="aqi_alert")
    rule = report.rules[0]
    assert rule.alert_type == "aqi_alert"
    assert rule.fired is False
    assert rule.data_available is False
    assert rule.status == STATUS_DATA_UNAVAILABLE


def test_report_fired_when_nws_heat_event_present() -> None:
    now = _now()
    with SessionLocal() as db:
        # Heat advisory reads three sources; seed all fresh so data_available
        # is True and the NWS event drives "fired".
        upsert_source(db, SOURCE_NWS_ALERTS, {"alerts": [{"event": "Heat Advisory"}]}, now=now)
        upsert_source(db, SOURCE_NWS_CURRENT, {"heat_index_f": 95}, now=now)
        upsert_source(db, SOURCE_NWS_FORECAST, {"forecast_high_f": 100}, now=now)
        db.commit()
        report = build_safety_report(db, alert_type_filter="heat_advisory", now=now)
    rule = report.rules[0]
    assert rule.fired is True
    assert rule.status == STATUS_FIRED
    assert rule.data_available is True
    assert all(s.present and not s.is_stale for s in rule.sources)


def test_report_clear_when_fresh_but_below_threshold() -> None:
    now = _now()
    with SessionLocal() as db:
        upsert_source(db, SOURCE_AIRNOW, {"current_aqi": 10}, now=now)
        db.commit()
        report = build_safety_report(db, alert_type_filter="aqi_alert", now=now)
    rule = report.rules[0]
    assert rule.fired is False
    assert rule.data_available is True
    assert rule.status == STATUS_CLEAR


def test_report_stale_source_is_unavailable_not_clear() -> None:
    now = _now()
    stale_at = now - timedelta(days=2)
    with SessionLocal() as db:
        # AirNow TTL is 1800s; fetched 2 days ago -> stale.
        upsert_source(db, SOURCE_AIRNOW, {"current_aqi": 10}, now=stale_at)
        db.commit()
        report = build_safety_report(db, alert_type_filter="aqi_alert", now=now)
    rule = report.rules[0]
    assert rule.data_available is False
    assert rule.status == STATUS_DATA_UNAVAILABLE
    assert rule.sources[0].is_stale is True


def test_report_writes_nothing() -> None:
    now = _now()
    with SessionLocal() as db:
        before = db.query(AlertDispatched).count()
        upsert_source(db, SOURCE_NWS_ALERTS, {"alerts": [{"event": "Heat Advisory"}]}, now=now)
        upsert_source(db, SOURCE_USGS, {"lake_gauge_ft": 1.0, "prior_gauge_ft": 10.0}, now=now)
        db.commit()
        build_safety_report(db, now=now)
        after = db.query(AlertDispatched).count()
    assert after == before


def test_report_to_dict_is_json_serializable() -> None:
    import json

    with SessionLocal() as db:
        report = build_safety_report(db)
    payload = json.dumps(report.to_dict())
    assert "\"rules\"" in payload
