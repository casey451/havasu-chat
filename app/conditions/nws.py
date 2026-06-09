"""NWS API client — alerts, current, forecast, sunset (Phase 8a)."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from app.conditions.constants import LHC_LAT, LHC_LON, NWS_USER_AGENT
from app.contrib.rate_limiter import SourceLimiter

logger = logging.getLogger(__name__)

_NWS_LIMITER = SourceLimiter("nws", qps=1.0)
_NWS_BASE = "https://api.weather.gov"

# Official Lake Havasu City METAR station (Lake Havasu City Airport). Pin it as
# the primary observation source so temp/wind are always in-town: NWS's
# "nearest station" ordering can otherwise surface an out-of-town RAWS/airfield
# site across the river. Only fall back to the nearest-station walk when KHII's
# latest observation carries no temperature.
LHC_PRIMARY_STATION = "KHII"


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


def _obs_temp_c(props: dict[str, Any]) -> float | None:
    """Pull the Celsius temperature value out of an observation's properties,
    tolerating a missing/null/non-dict `temperature` field."""
    temperature = props.get("temperature")
    if not isinstance(temperature, dict):
        return None
    value = temperature.get("value")
    return value if isinstance(value, (int, float)) else None


def _build_current(props: dict[str, Any]) -> dict[str, Any]:
    """Shape an observation's properties into the current-conditions payload.
    Temperature/heat-index are converted C→F; wind speed m/s→mph."""
    temp_c = _obs_temp_c(props)
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


def fetch_nws_current() -> dict[str, Any]:
    # Try the pinned official LHC station (KHII) first so temp/wind are always
    # in-town. Only fall through to the nearest-station walk when KHII's latest
    # observation is unavailable or carries no temperature.
    try:
        latest = _get(f"/stations/{LHC_PRIMARY_STATION}/observations/latest")
        props = latest.get("properties") or {}
        if _obs_temp_c(props) is not None:
            return _build_current(props)
    except Exception:
        logger.warning(
            "KHII primary obs unavailable; falling back to nearest-station walk"
        )

    points = _grid_points()
    stations_url = (points.get("properties") or {}).get("observationStations")
    if not stations_url:
        raise RuntimeError("NWS points missing observationStations")
    stations = _get(stations_url)
    station_features = stations.get("features") or []
    if not station_features:
        raise RuntimeError("NWS no observation stations")

    # The nearest station's latest observation frequently reports a null
    # temperature (sensor gaps); walk the first few stations and keep the
    # first observation that actually carries one. Falls back to the first
    # station's (temp-less) observation so wind/heat-index still surface.
    props = {}
    for feature in station_features[:3]:
        station_url = (feature.get("id") or "").strip()
        if not station_url:
            continue
        latest = _get(f"{station_url}/observations/latest")
        candidate = latest.get("properties") or {}
        if not props:
            props = candidate
        if _obs_temp_c(candidate) is not None:
            props = candidate
            break
    if not props:
        raise RuntimeError("NWS station id missing")
    return _build_current(props)


def fetch_nws_forecast_daily() -> dict[str, Any]:
    points = _grid_points()
    forecast_url = (points.get("properties") or {}).get("forecast")
    if not forecast_url:
        raise RuntimeError("NWS points missing forecast")
    forecast = _get(forecast_url)
    periods = (forecast.get("properties") or {}).get("periods") or []
    daily_high_f: float | None = None
    short_forecast: str | None = None
    if periods and isinstance(periods[0], dict):
        temp = periods[0].get("temperature")
        if isinstance(temp, (int, float)):
            daily_high_f = float(temp)
        # Surface the first/current period's sky condition (e.g. "Sunny",
        # "Mostly Cloudy") so the home utility strip can render a sky chip.
        sf = periods[0].get("shortForecast")
        if isinstance(sf, str) and sf.strip():
            short_forecast = sf.strip()
    return {
        "periods": periods[:14],
        "forecast_high_f": daily_high_f,
        "short_forecast": short_forecast,
    }


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
