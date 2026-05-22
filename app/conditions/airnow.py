"""AirNow current AQI fetcher (Phase 8a)."""

from __future__ import annotations

import os
from math import asin, cos, radians, sin, sqrt
from typing import Any

import httpx

from app.conditions.constants import LHC_LAT, LHC_LON
from app.contrib.rate_limiter import SourceLimiter

_AIRNOW_LIMITER = SourceLimiter("airnow", qps=0.5)
_AIRNOW_URL = "https://www.airnowapi.org/aq/observation/zipCode/current/"
_EARTH_RADIUS_MI = 3958.7613


def _haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in statute miles between two lat/lon pairs."""
    lat1_r, lat2_r = radians(lat1), radians(lat2)
    dlat = lat2_r - lat1_r
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_MI * asin(sqrt(a))


def fetch_airnow_current() -> dict[str, Any]:
    """Return normalized AirNow payload for cache row ``airnow_86403``."""
    api_key = (os.environ.get("AIRNOW_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("AIRNOW_API_KEY not set")

    zip_code = os.environ.get("AIRNOW_ZIP", "86403")
    distance_mi = int(os.environ.get("AIRNOW_DISTANCE_MI", "100"))

    def _inner(client: httpx.Client) -> httpx.Response:
        return client.get(
            _AIRNOW_URL,
            params={
                "format": "application/json",
                "zipCode": zip_code,
                "distance": distance_mi,
                "API_KEY": api_key,
            },
            timeout=10.0,
        )

    with httpx.Client() as client:
        # SourceLimiter.call_with_retry takes a no-arg callable; close over
        # `client` via lambda (Phase 8a.0 hotfix 2026-05-21 — original signature
        # passed `client` as a second positional arg → TypeError swallowed by
        # outer with_retry as "exhausted").
        response = _AIRNOW_LIMITER.call_with_retry(lambda: _inner(client))
    if response is None:
        raise RuntimeError("AirNow request failed after retries")
    response.raise_for_status()
    raw = response.json()
    rows: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                rows.append(item)

    primary = rows[0] if rows else {}
    aqi = primary.get("AQI")
    try:
        aqi_int = int(aqi) if aqi is not None else None
    except (TypeError, ValueError):
        aqi_int = None

    # Compute great-circle distance from LHC to the AirNow station via the
    # station's Latitude/Longitude. AirNow's `zipCode/current/` endpoint does
    # NOT return a "Distance" field (the original Phase 8a fetcher's
    # `primary.get("Distance")` was silently storing None every cycle — see
    # gotcha #23 in docs/maintainability/dispatch_channels.md for the
    # attribution-chip UX contract this populates).
    lat_raw = primary.get("Latitude")
    lon_raw = primary.get("Longitude")
    try:
        if lat_raw is not None and lon_raw is not None:
            distance_mi: float | None = round(
                _haversine_mi(LHC_LAT, LHC_LON, float(lat_raw), float(lon_raw)), 1
            )
        else:
            distance_mi = None
    except (TypeError, ValueError):
        distance_mi = None

    return {
        "rows": rows,
        "current_aqi": aqi_int,
        "current_aqi_parameter": primary.get("ParameterName"),
        "aqi_source_station_name": primary.get("SiteName") or primary.get("ReportingArea"),
        "aqi_source_state_code": primary.get("StateCode"),
        "aqi_source_distance_mi": distance_mi,
        "category_name": primary.get("Category", {}).get("Name")
        if isinstance(primary.get("Category"), dict)
        else primary.get("CategoryName"),
    }
