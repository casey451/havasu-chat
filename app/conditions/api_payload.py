"""Assemble /api/conditions JSON from cache rows (Phase 8a)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.conditions.cache import read_source
from app.conditions.constants import (
    SOURCE_AIRNOW,
    SOURCE_NWS_ALERTS,
    SOURCE_NWS_CURRENT,
    SOURCE_NWS_FORECAST,
    SOURCE_OPENUV,
    SOURCE_RISE_WATER_TEMP,
    SOURCE_USGS,
    SOURCE_USGS_WATER_TEMP,
)
from app.conditions.staleness import staleness_label
from app.conditions.sun import sunset_utc
from app.core.timezone import LAKE_HAVASU_TZ

logger = logging.getLogger(__name__)

# Water temp is a slow (roughly daily) feed with a 6h cache TTL, so it reads
# "fresh" for the whole window rather than flashing stale after the default 2h.
_WATER_TEMP_STALE_AFTER_HOURS = 6
# Throttle the WATER_TEMP_STALE observability log to at most once per hour so a
# stale/omitted gage doesn't spam the logs on every /api/conditions build.
_WATER_TEMP_STALE_LOG_INTERVAL = timedelta(hours=1)
_last_water_temp_stale_log: datetime | None = None


def _log_water_temp_stale(now: datetime, reason: str, attribution: str | None) -> None:
    """Emit a WATER_TEMP_STALE marker at most once per hour (process-wide)."""
    global _last_water_temp_stale_log
    last = _last_water_temp_stale_log
    if last is not None and (now - last) < _WATER_TEMP_STALE_LOG_INTERVAL:
        return
    _last_water_temp_stale_log = now
    logger.warning("WATER_TEMP_STALE reason=%s source=%s", reason, attribution or "none")

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
    """Render a sunset ISO timestamp as Lake Havasu wall-clock, e.g. ``7:42 PM``.

    Source-agnostic: the ISO may be Open-UV's true sunset or the locally computed
    astronomical sunset (:mod:`app.conditions.sun`). Converts to America/Phoenix
    and strips any leading zero from the hour (Windows-safe).
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

    # Water temperature. Prefer the Reclamation RISE reading at Parker Dam (item
    # 6127) — Parker Dam impounds Lake Havasu, so it's the representative main-
    # lake value — and fall back to the USGS Bill Williams gage (09426630), which
    # has published the -100000 sentinel since 2026-05-21 (water_temp_f None).
    # Each self-gates at the fetcher on its feature flag, so a row with
    # feature_enabled=False or a null reading is simply not chosen and
    # /api/conditions stays unchanged.
    def _live_water_temp(row) -> bool:
        return (
            row is not None
            and isinstance(row.data, dict)
            and bool(row.data.get("feature_enabled"))
            and row.data.get("water_temp_f") is not None
        )

    rise_wt = read_source(db, SOURCE_RISE_WATER_TEMP, now=now)
    usgs_wt = read_source(db, SOURCE_USGS_WATER_TEMP, now=now)
    if _live_water_temp(rise_wt):
        chosen_wt, wt_attribution = rise_wt, "Reclamation · Parker Dam"
    elif _live_water_temp(usgs_wt):
        chosen_wt, wt_attribution = usgs_wt, "USGS 09426630 ~25mi south"
    else:
        chosen_wt, wt_attribution = None, None
    if chosen_wt is not None:
        d = chosen_wt.data
        # 6h window (matches the RISE cache TTL) so a daily reading doesn't flash
        # "stale" 2h after each cron tick.
        label, stale = staleness_label(
            chosen_wt.fetched_at, now, stale_after_hours=_WATER_TEMP_STALE_AFTER_HOURS
        )
        is_stale = stale or chosen_wt.is_stale
        payload.update(
            {
                "water_temp_c": d.get("water_temp_c"),
                "water_temp_f": d.get("water_temp_f"),
                "water_temp_attribution": wt_attribution,
                "water_temp_updated_at_iso": _iso(chosen_wt.fetched_at),
                "water_temp_staleness_label": label,
                "water_temp_is_stale": is_stale,
            }
        )
        if is_stale:
            _log_water_temp_stale(now, "stale_reading", wt_attribution)
    else:
        # Honest-omit: no live gage reading. Only flag it in the logs when a gage
        # was ENABLED but returned nothing (a real fetch/parse failure worth
        # noticing) — not when both flags are intentionally OFF (the default).
        def _enabled_but_empty(row: Any) -> bool:
            return (
                row is not None
                and isinstance(row.data, dict)
                and bool(row.data.get("feature_enabled"))
            )

        if _enabled_but_empty(rise_wt) or _enabled_but_empty(usgs_wt):
            _log_water_temp_stale(now, "no_live_reading", None)

    # Sunset: PREFER the true astronomical sunset from Open-UV
    # (sun_info.sun_times.sunset, stored on the SOURCE_OPENUV row as
    # ``sunset_iso``). When Open-UV is absent, COMPUTE the astronomical sunset
    # for the city's coordinates (app.conditions.sun) rather than falling back to
    # the old NWS evening-forecast-period start, which read ~2h early ("Sunset
    # 6:00 PM" in late June — site review §4c). The computed value is
    # deterministic, always available, and never stale.
    # Only trust Open-UV's sunset while the row is FRESH — a stale row carries an
    # old day's sunset_iso, which is wrong for today, so we compute instead.
    openuv_sunset_iso = None
    openuv_label = None
    if openuv_row is not None and isinstance(openuv_row.data, dict):
        candidate = openuv_row.data.get("sunset_iso")
        if isinstance(candidate, str) and candidate.strip():
            openuv_label, openuv_stale = staleness_label(openuv_row.fetched_at, now)
            if not (openuv_stale or openuv_row.is_stale):
                openuv_sunset_iso = candidate.strip()

    if openuv_sunset_iso is not None:
        sunset_local = _format_sunset_local(openuv_sunset_iso)
        if sunset_local is not None:
            payload.update(
                {
                    "sunset_iso": openuv_sunset_iso,
                    "sunset_local": sunset_local,
                    "sunset_source": "openuv",
                    "sunset_updated_at_iso": _iso(openuv_row.fetched_at),
                    "sunset_staleness_label": openuv_label,
                    "sunset_is_stale": False,
                }
            )
    else:
        local_date = now.replace(tzinfo=UTC).astimezone(LAKE_HAVASU_TZ).date()
        computed_iso = _iso(sunset_utc(local_date))
        payload.update(
            {
                "sunset_iso": computed_iso,
                "sunset_local": _format_sunset_local(computed_iso),
                "sunset_source": "computed",
                "sunset_updated_at_iso": None,
                "sunset_staleness_label": None,
                "sunset_is_stale": False,
            }
        )

    return payload
