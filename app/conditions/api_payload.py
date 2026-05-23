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
    SOURCE_USGS,
    SOURCE_USGS_WATER_TEMP,
)
from app.conditions.staleness import staleness_label


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
        payload.update(
            {
                "current_temp_f": d.get("temperature_f"),
                "heat_index_f": d.get("heat_index_f"),
                "wind_speed_mph": d.get("wind_speed_mph"),
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

    return payload
