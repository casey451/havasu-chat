"""NWS API client — alerts, current, forecast, sunset (Phase 8a)."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx

from app.conditions.constants import LHC_LAT, LHC_LON, NWS_USER_AGENT
from app.contrib.rate_limiter import SourceLimiter

_NWS_LIMITER = SourceLimiter("nws", qps=1.0)
_NWS_BASE = "https://api.weather.gov"


def _headers() -> dict[str, str]:
    ua = os.environ.get("NWS_USER_AGENT", NWS_USER_AGENT)
    return {"User-Agent": ua, "Accept": "application/geo+json"}


def _get(path: str, *, timeout: float = 10.0) -> dict[str, Any]:
    url = path if path.startswith("http") else f"{_NWS_BASE}{path}"

    def _inner(client: httpx.Client) -> httpx.Response:
        return client.get(url, headers=_headers(), timeout=timeout)

    with httpx.Client() as client:
        # Phase 8a.0 hotfix 2026-05-21: SourceLimiter.call_with_retry takes a
        # no-arg callable; close over `client` via lambda.
        response = _NWS_LIMITER.call_with_retry(lambda: _inner(client))
    if response is None:
        raise RuntimeError(f"NWS request failed: {path}")
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


def fetch_nws_alerts_lhc_zone() -> dict[str, Any]:
    zone_id = os.environ.get("LHC_NWS_ZONE_ID", "AZZ002")
    payload = _get(f"/alerts/active?zone={zone_id}")
    features = payload.get("features") or []
    alerts: list[dict[str, Any]] = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        props = feat.get("properties") or {}
        if not isinstance(props, dict):
            continue
        alerts.append(
            {
                "event": props.get("event"),
                "headline": props.get("headline"),
                "description": props.get("description"),
                "severity": props.get("severity"),
                "ends": props.get("ends"),
            }
        )
    return {"zone_id": zone_id, "alerts": alerts, "active_nws_alerts": alerts}


def _grid_points() -> dict[str, Any]:
    return _get(f"/points/{LHC_LAT},{LHC_LON}")


def fetch_nws_current() -> dict[str, Any]:
    points = _grid_points()
    stations_url = (points.get("properties") or {}).get("observationStations")
    if not stations_url:
        raise RuntimeError("NWS points missing observationStations")
    stations = _get(stations_url)
    station_features = stations.get("features") or []
    if not station_features:
        raise RuntimeError("NWS no observation stations")
    station_url = (station_features[0].get("id") or "").strip()
    if not station_url:
        raise RuntimeError("NWS station id missing")
    latest = _get(f"{station_url}/observations/latest")
    props = latest.get("properties") or {}
    temp_c = props.get("temperature", {}).get("value") if isinstance(
        props.get("temperature"), dict
    ) else None
    temp_f: float | None = None
    if temp_c is not None:
        temp_f = float(temp_c) * 9.0 / 5.0 + 32.0
    heat_index_f = props.get("heatIndex", {}).get("value")
    if isinstance(heat_index_f, (int, float)):
        heat_index_f = float(heat_index_f) * 9.0 / 5.0 + 32.0
    else:
        heat_index_f = None
    wind_speed = props.get("windSpeed", {}).get("value")
    wind_direction = props.get("windDirection", {}).get("value")
    return {
        "temperature_f": temp_f,
        "heat_index_f": heat_index_f,
        "wind_speed_mph": float(wind_speed) * 0.621371 if wind_speed else None,
        "wind_direction_deg": wind_direction,
        "timestamp": props.get("timestamp"),
    }


def fetch_nws_forecast_daily() -> dict[str, Any]:
    points = _grid_points()
    forecast_url = (points.get("properties") or {}).get("forecast")
    if not forecast_url:
        raise RuntimeError("NWS points missing forecast")
    forecast = _get(forecast_url)
    periods = (forecast.get("properties") or {}).get("periods") or []
    daily_high_f: float | None = None
    if periods and isinstance(periods[0], dict):
        temp = periods[0].get("temperature")
        if isinstance(temp, (int, float)):
            daily_high_f = float(temp)
    return {"periods": periods[:14], "forecast_high_f": daily_high_f}


def fetch_nws_sunset() -> dict[str, Any]:
    points = _grid_points()
    forecast_url = (points.get("properties") or {}).get("forecast")
    if not forecast_url:
        raise RuntimeError("NWS points missing forecast for sunset")
    forecast = _get(forecast_url)
    periods = (forecast.get("properties") or {}).get("periods") or []
    sunset_local: str | None = None
    for period in periods:
        if not isinstance(period, dict):
            continue
        name = (period.get("name") or "").lower()
        if "tonight" in name or "this evening" in name:
            sunset_local = period.get("startTime")
            break
    return {"sunset_iso": sunset_local, "periods": periods[:2]}


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None
