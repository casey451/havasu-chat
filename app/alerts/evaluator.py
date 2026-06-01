"""Evaluate cache state vs alert thresholds (Phase 8a)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.alerts.thresholds import (
    AQI_ALERT_THRESHOLD,
    EVENT_TRAFFIC_DEFERRED,
    HEAT_ADVISORY_FORECAST_THRESHOLD_F,
    HEAT_ADVISORY_INDEX_FLOOR_F,
    HEAT_ADVISORY_NWS_EVENT_PATTERNS,
    LAKE_HAZARD_GAUGE_DROP_FT,
    LAKE_HAZARD_NWS_KEYWORDS,
)
from app.conditions.cache import read_source
from app.conditions.constants import (
    SOURCE_AIRNOW,
    SOURCE_NWS_ALERTS,
    SOURCE_NWS_CURRENT,
    SOURCE_NWS_FORECAST,
    SOURCE_USGS,
)


@dataclass(frozen=True)
class AlertEvaluation:
    fired: bool
    trigger_data: dict[str, Any]


def _nws_event_matches(event: str | None, patterns: tuple[str, ...]) -> bool:
    if not event:
        return False
    lower = event.lower()
    return any(p.lower() in lower for p in patterns)


def _nws_keyword_match(alerts: list[Any]) -> bool:
    for item in alerts:
        if not isinstance(item, dict):
            continue
        blob = " ".join(
            str(item.get(k) or "") for k in ("event", "headline", "description")
        ).lower()
        if any(kw in blob for kw in LAKE_HAZARD_NWS_KEYWORDS):
            return True
    return False


def evaluate_heat_advisory(db: Session) -> AlertEvaluation:
    alerts_row = read_source(db, SOURCE_NWS_ALERTS)
    current_row = read_source(db, SOURCE_NWS_CURRENT)
    forecast_row = read_source(db, SOURCE_NWS_FORECAST)

    nws_fired = False
    matched_events: list[str] = []
    if alerts_row and not alerts_row.is_stale:
        for item in alerts_row.data.get("alerts") or alerts_row.data.get("active_nws_alerts") or []:
            if not isinstance(item, dict):
                continue
            ev = item.get("event")
            if _nws_event_matches(ev, HEAT_ADVISORY_NWS_EVENT_PATTERNS):
                nws_fired = True
                matched_events.append(str(ev))

    forecast_high: float | None = None
    if forecast_row and not forecast_row.is_stale:
        fh = forecast_row.data.get("forecast_high_f")
        if isinstance(fh, (int, float)):
            forecast_high = float(fh)

    forecast_fired = (
        forecast_high is not None and forecast_high > HEAT_ADVISORY_FORECAST_THRESHOLD_F
    )

    index_fired = False
    heat_index: float | None = None
    if current_row and not current_row.is_stale:
        hi = current_row.data.get("heat_index_f")
        if isinstance(hi, (int, float)):
            heat_index = float(hi)
        if HEAT_ADVISORY_INDEX_FLOOR_F is not None and heat_index is not None:
            index_fired = heat_index >= HEAT_ADVISORY_INDEX_FLOOR_F

    fired = nws_fired or forecast_fired or index_fired
    return AlertEvaluation(
        fired=fired,
        trigger_data={
            "nws_events": matched_events,
            "forecast_high_f": forecast_high,
            "heat_index_f": heat_index,
            "forecast_threshold_f": HEAT_ADVISORY_FORECAST_THRESHOLD_F,
        },
    )


def evaluate_aqi_alert(db: Session) -> AlertEvaluation:
    row = read_source(db, SOURCE_AIRNOW)
    if row is None or row.is_stale:
        return AlertEvaluation(fired=False, trigger_data={"reason": "stale_or_missing"})

    rows = row.data.get("rows") or []
    if not rows and row.data.get("current_aqi") is not None:
        rows = [row.data]

    worst_aqi: int | None = None
    worst_param: str | None = None
    for item in rows:
        if not isinstance(item, dict):
            continue
        aqi = item.get("AQI") or item.get("current_aqi")
        try:
            aqi_int = int(aqi) if aqi is not None else None
        except (TypeError, ValueError):
            aqi_int = None
        if aqi_int is not None and (worst_aqi is None or aqi_int > worst_aqi):
            worst_aqi = aqi_int
            worst_param = item.get("ParameterName") or item.get("current_aqi_parameter")

    fired = worst_aqi is not None and worst_aqi > AQI_ALERT_THRESHOLD
    return AlertEvaluation(
        fired=fired,
        trigger_data={
            "worst_aqi": worst_aqi,
            "parameter": worst_param,
            "threshold": AQI_ALERT_THRESHOLD,
        },
    )


def evaluate_lake_hazard(db: Session) -> AlertEvaluation:
    alerts_row = read_source(db, SOURCE_NWS_ALERTS)
    usgs_row = read_source(db, SOURCE_USGS)

    nws_fired = False
    if alerts_row and not alerts_row.is_stale:
        alerts = alerts_row.data.get("alerts") or alerts_row.data.get("active_nws_alerts") or []
        nws_fired = _nws_keyword_match(alerts if isinstance(alerts, list) else [])

    gauge_drop_fired = False
    gauge_ft: float | None = None
    prior_ft: float | None = None
    if usgs_row and not usgs_row.is_stale:
        gauge_ft = usgs_row.data.get("lake_gauge_ft")
        prior_ft = usgs_row.data.get("prior_gauge_ft")
        if isinstance(gauge_ft, (int, float)) and isinstance(prior_ft, (int, float)):
            drop = float(prior_ft) - float(gauge_ft)
            gauge_drop_fired = drop > LAKE_HAZARD_GAUGE_DROP_FT

    fired = nws_fired or gauge_drop_fired
    return AlertEvaluation(
        fired=fired,
        trigger_data={
            "nws_keyword_match": nws_fired,
            "gauge_ft": gauge_ft,
            "prior_gauge_ft": prior_ft,
            "drop_threshold_ft": LAKE_HAZARD_GAUGE_DROP_FT,
        },
    )


def evaluate_alert_type(db: Session, alert_type: str) -> AlertEvaluation:
    if alert_type == EVENT_TRAFFIC_DEFERRED:
        return AlertEvaluation(fired=False, trigger_data={"deferred": True})
    if alert_type == "heat_advisory":
        return evaluate_heat_advisory(db)
    if alert_type == "aqi_alert":
        return evaluate_aqi_alert(db)
    if alert_type == "lake_hazard":
        return evaluate_lake_hazard(db)
    return AlertEvaluation(fired=False, trigger_data={"unknown_type": alert_type})
