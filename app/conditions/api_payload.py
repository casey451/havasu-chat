"""Assemble /api/conditions JSON from cache rows (Phase 8a)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.conditions.cache import read_source
from app.conditions.constants import (
    SOURCE_AIRNOW,
    SOURCE_NWS_ALERTS,
    SOURCE_NWS_CURRENT,
    SOURCE_NWS_FORECAST,
    SOURCE_NWS_SUNSET,
    SOURCE_OPENUV,
    SOURCE_USGS,
    SOURCE_USGS_WATER_TEMP,
)
from app.conditions.staleness import staleness_label
from app.core.timezone import LAKE_HAVASU_TZ

_COMPASS_16 = (
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
)


def degrees_to_cardinal(deg: float | int | None) -> str | None:
    """Convert a wind-direction bearing in degrees to a 16-point compass label.

    Returns ``None`` when ``deg`` is ``None`` or not a finite number so callers
    can omit the field cleanly. Degrees are normalized into ``[0, 360)`` first,
    so values outside that range (e.g. 360, -45) still map sensibly.
    """
    if not isinstance(deg, (int, float)) or isinstance(deg, bool):
        return None
    try:
        value = float(deg)
    except (TypeError, ValueError):
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    normalized = value % 360.0
    index = int((normalized + 11.25) // 22.5) % 16
    return _COMPASS_16[index]


def _format_sunset_local(sunset_iso: str | None) -> str | None:
    """Render an NWS sunset ISO timestamp as Lake Havasu wall-clock, e.g. ``7:42 PM``.

    The NWS sunset source stores the tonight/evening period startTime, which is
    an approximation of sunset rather than an astronomical value. We convert to
    America/Phoenix and strip any leading zero from the hour (Windows-safe).
    """
    if not sunset_iso:
        return None
    try:
        parsed = datetime.fromisoformat(str(sunset_iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    local = parsed.astimezone(LAKE_HAVASU_TZ)
    stamp = local.strftime("%I:%M %p")
    if stamp.startswith("0"):
        stamp = stamp[1:]
    return stamp


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def build_conditions_api_payload(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC).replace(tzinfo=None)
    payload: dict[str, Any] = {"rendered_at_iso": _iso(now)}

    airnow = read_source(db, SOURCE_AIRNOW, now=now)
    if airnow is not None:
        d = airnow.data
        label, stale = staleness_label(airnow.fetched_at, now)
        payload.update(
            {
                "current_aqi": d.get("current_aqi"),
                "current_aqi_parameter": d.get("current_aqi_parameter"),
                "aqi_source_station_name": d.get("aqi_source_station_name"),
                "aqi_source_state_code": d.get("aqi_source_state_code"),
                "aqi_source_distance_mi": d.get("aqi_source_distance_mi"),
                "aqi_updated_at_iso": _iso(airnow.fetched_at),
                "aqi_staleness_label": label,
                "aqi_is_stale": stale or airnow.is_stale,
            }
        )

    nws_current = read_source(db, SOURCE_NWS_CURRENT, now=now)
    if nws_current is not None:
        d = nws_current.data
        label, stale = staleness_label(nws_current.fetched_at, now)
        wind_dir_deg = d.get("wind_direction_deg")
        payload.update(
            {
                "current_temp_f": d.get("temperature_f"),
                "heat_index_f": d.get("heat_index_f"),
                "wind_speed_mph": d.get("wind_speed_mph"),
                "wind_direction_deg": wind_dir_deg,
                "wind_direction_cardinal": degrees_to_cardinal(wind_dir_deg),
                "temp_updated_at_iso": _iso(nws_current.fetched_at),
                "temp_staleness_label": label,
                "temp_is_stale": stale or nws_current.is_stale,
            }
        )

    nws_alerts = read_source(db, SOURCE_NWS_ALERTS, now=now)
    if nws_alerts is not None:
        d = nws_alerts.data
        label, stale = staleness_label(nws_alerts.fetched_at, now)
        payload.update(
            {
                "active_nws_alerts": d.get("active_nws_alerts") or d.get("alerts") or [],
                "alerts_updated_at_iso": _iso(nws_alerts.fetched_at),
                "alerts_staleness_label": label,
                "alerts_is_stale": stale or nws_alerts.is_stale,
            }
        )

    # Sky/condition text (e.g. "Sunny", "Mostly Cloudy") sourced from the NWS
    # daily forecast's first/current period shortForecast. Emitted only when
    # present so /api/conditions stays unchanged when the forecast is absent.
    nws_forecast = read_source(db, SOURCE_NWS_FORECAST, now=now)
    if nws_forecast is not None:
        d = nws_forecast.data
        sky = d.get("short_forecast")
        if isinstance(sky, str) and sky.strip():
            label, stale = staleness_label(nws_forecast.fetched_at, now)
            payload.update(
                {
                    "sky_condition": sky.strip(),
                    "sky_updated_at_iso": _iso(nws_forecast.fetched_at),
                    "sky_staleness_label": label,
                    "sky_is_stale": stale or nws_forecast.is_stale,
                }
            )

    openuv_row = read_source(db, SOURCE_OPENUV, now=now)
    if openuv_row is not None and isinstance(openuv_row.data, dict):
        uv = openuv_row.data.get("uv_index")
        if isinstance(uv, (int, float)):
            label, stale = staleness_label(openuv_row.fetched_at, now)
            payload.update(
                {
                    "uv_index": float(uv),
                    "uv_max": openuv_row.data.get("uv_max"),
                    "uv_severity": openuv_row.data.get("uv_severity") or "neutral",
                    # uv_source distinguishes the live Open-UV reading from the
                    # keyless EPA forecast fallback so the tile attributes
                    # honestly; default to Open-UV for rows written before the
                    # robust fetcher landed.
                    "uv_source": openuv_row.data.get("uv_source") or "Open-UV",
                    "uv_updated_at_iso": _iso(openuv_row.fetched_at),
                    "uv_staleness_label": label,
                    "uv_is_stale": stale or openuv_row.is_stale,
                }
            )

    usgs = read_source(db, SOURCE_USGS, now=now)
    if usgs is not None:
        d = usgs.data
        label, stale = staleness_label(usgs.fetched_at, now)
        payload.update(
            {
                "lake_gauge_ft": d.get("lake_gauge_ft"),
                "lake_storage_acft": d.get("lake_storage_acft"),
                "lake_updated_at_iso": _iso(usgs.fetched_at),
                "lake_staleness_label": label,
                "lake_is_stale": stale or usgs.is_stale,
            }
        )

    # V1.5 wave 3: water-temperature signal from USGS 09426630, gated at the
    # api-payload boundary on the cache row's feature_enabled flag. The
    # fetcher writes feature_enabled=False when the env flag is OFF (and
    # makes no HTTP request); we honor that here by skipping field emission
    # so /api/conditions stays bit-for-bit unchanged in flag-OFF prod state.
    water_temp = read_source(db, SOURCE_USGS_WATER_TEMP, now=now)
    if water_temp is not None:
        d = water_temp.data
        if d.get("feature_enabled"):
            label, stale = staleness_label(water_temp.fetched_at, now)
            payload.update(
                {
                    "water_temp_c": d.get("water_temp_c"),
                    "water_temp_f": d.get("water_temp_f"),
                    "water_temp_updated_at_iso": _iso(water_temp.fetched_at),
                    "water_temp_staleness_label": label,
                    "water_temp_is_stale": stale or water_temp.is_stale,
                }
            )

    # Sunset: PREFER the true astronomical sunset from Open-UV
    # (sun_info.sun_times.sunset, stored on the SOURCE_OPENUV row as
    # ``sunset_iso``). Fall back to the SOURCE_NWS_SUNSET row, whose ``sunset_iso``
    # is the tonight/evening forecast-period startTime -- an approximation that
    # runs ~1-2h early. We surface the raw ISO plus a Lake-Havasu-local formatted
    # string so both the JSON API and the /today Lake Light strip can render it.
    # Emitted only when a usable ISO is present so /api/conditions stays unchanged
    # when both sources are absent.
    openuv_sunset_iso = None
    if openuv_row is not None and isinstance(openuv_row.data, dict):
        candidate = openuv_row.data.get("sunset_iso")
        if isinstance(candidate, str) and candidate.strip():
            openuv_sunset_iso = candidate.strip()

    if openuv_sunset_iso is not None:
        sunset_local = _format_sunset_local(openuv_sunset_iso)
        if sunset_local is not None:
            label, stale = staleness_label(openuv_row.fetched_at, now)
            payload.update(
                {
                    "sunset_iso": openuv_sunset_iso,
                    "sunset_local": sunset_local,
                    "sunset_source": "openuv",
                    "sunset_updated_at_iso": _iso(openuv_row.fetched_at),
                    "sunset_staleness_label": label,
                    "sunset_is_stale": stale or openuv_row.is_stale,
                }
            )
    else:
        sunset_row = read_source(db, SOURCE_NWS_SUNSET, now=now)
        if sunset_row is not None and isinstance(sunset_row.data, dict):
            sunset_iso = sunset_row.data.get("sunset_iso")
            sunset_local = _format_sunset_local(sunset_iso) if sunset_iso else None
            if sunset_local is not None:
                label, stale = staleness_label(sunset_row.fetched_at, now)
                payload.update(
                    {
                        "sunset_iso": sunset_iso,
                        "sunset_local": sunset_local,
                        "sunset_source": "nws_approx",
                        "sunset_updated_at_iso": _iso(sunset_row.fetched_at),
                        "sunset_staleness_label": label,
                        "sunset_is_stale": stale or sunset_row.is_stale,
                    }
                )

    return payload
