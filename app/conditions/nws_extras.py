"""nws_extras — extra NWS gridpoint fields + Lake Wind Advisory zone check.

source-expansion #14. The raw NWS gridpoint payload
``https://api.weather.gov/gridpoints/VEF/141,19`` carries boater/heat fields the
current conditions pipeline doesn't surface: ``windGust``, ``heatRisk``,
``wetBulbGlobeTemperature``, and ``twentyFootWind*``. This module parses them
into cache-ready fields. It also checks whether the Lake Wind Advisory zone
**AZZ036** is covered by the alerts filter (which currently defaults to the
city zone AZZ002).

INERT build-only module: it provides parsing + a coverage check but is NOT wired
into the live conditions fetcher (that registration is the integration step).
The gridpoint fetch reuses the existing nws client (UA + SourceLimiter).
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from app.conditions import nws

logger = logging.getLogger(__name__)

SOURCE = "nws_extras"
GRIDPOINT_URL = "https://api.weather.gov/gridpoints/VEF/141,19"
LAKE_WIND_ADVISORY_ZONE = "AZZ036"

_C_TO_F = lambda c: float(c) * 9.0 / 5.0 + 32.0  # noqa: E731
_KMH_TO_MPH = 0.621371


def _select_current_value(prop: Any, *, now: datetime) -> tuple[float | None, str | None]:
    """Return (value, uom) for the time-series entry covering ``now`` (else first)."""
    if not isinstance(prop, dict):
        return None, None
    uom = prop.get("uom")
    values = prop.get("values")
    if not isinstance(values, list) or not values:
        return None, uom
    chosen = None
    for entry in values:
        if not isinstance(entry, dict):
            continue
        valid = entry.get("validTime") or ""
        start = valid.split("/")[0] if "/" in valid else valid
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            continue
        if start_dt.tzinfo is not None:
            start_dt = start_dt.astimezone(UTC).replace(tzinfo=None)
        if start_dt <= now:
            chosen = entry.get("value")
        else:
            break
    if chosen is None:
        chosen = values[0].get("value") if isinstance(values[0], dict) else None
    return (float(chosen) if isinstance(chosen, (int, float)) else None), uom


def _to_mph(value: float | None, uom: str | None) -> float | None:
    if value is None:
        return None
    if uom and "km_h" in uom:
        return round(value * _KMH_TO_MPH, 1)
    if uom and ("m_s" in uom or "m/s" in uom):
        return round(value * 2.236936, 1)
    return round(value, 1)  # assume mph / unitless


def _to_f(value: float | None, uom: str | None) -> float | None:
    if value is None:
        return None
    if uom and "degC" in uom:
        return round(_C_TO_F(value), 1)
    return round(value, 1)


def parse_gridpoint(payload: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Parse the boater/heat extras from a gridpoint payload. Missing fields omitted."""
    now = now or datetime.now(UTC).replace(tzinfo=None)
    props = payload.get("properties") if isinstance(payload, dict) else None
    if not isinstance(props, dict):
        return {}
    out: dict[str, Any] = {}

    gust_v, gust_u = _select_current_value(props.get("windGust"), now=now)
    gust = _to_mph(gust_v, gust_u)
    if gust is not None:
        out["wind_gust_mph"] = gust

    tfw_v, tfw_u = _select_current_value(props.get("twentyFootWindSpeed"), now=now)
    tfw = _to_mph(tfw_v, tfw_u)
    if tfw is not None:
        out["twenty_foot_wind_mph"] = tfw

    wbgt_v, wbgt_u = _select_current_value(props.get("wetBulbGlobeTemperature"), now=now)
    wbgt = _to_f(wbgt_v, wbgt_u)
    if wbgt is not None:
        out["wet_bulb_globe_temp_f"] = wbgt

    hr_v, _ = _select_current_value(props.get("heatRisk"), now=now)
    if hr_v is not None:
        out["heat_risk"] = hr_v

    return out


def fetch_gridpoint_extras() -> dict[str, Any]:
    """Fetch the raw gridpoint and parse the extras (reuses nws._get pacing/UA)."""
    payload = nws._get(GRIDPOINT_URL)
    return parse_gridpoint(payload)


def lake_wind_advisory_zone_covered(configured_zone: str | None = None) -> bool:
    """True iff the Lake Wind Advisory zone AZZ036 is in the configured alert zone(s).

    The alerts fetcher uses LHC_NWS_ZONE_ID (default AZZ002 — the city zone),
    which does NOT include AZZ036. A False result is the expected finding today
    and means the alerts filter should add AZZ036 to catch lake wind advisories.
    """
    raw = configured_zone if configured_zone is not None else os.environ.get("LHC_NWS_ZONE_ID", "AZZ002")
    zones = {z.strip().upper() for z in raw.replace(";", ",").split(",") if z.strip()}
    return LAKE_WIND_ADVISORY_ZONE in zones
