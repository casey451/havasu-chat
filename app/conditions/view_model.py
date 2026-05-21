"""Conditions strip view-model for home.html (Phase 8a)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.conditions.api_payload import build_conditions_api_payload


@dataclass(frozen=True)
class ConditionsTile:
    kind: str
    primary_value: str
    secondary_value: str | None
    attribution_chip: str | None
    severity: str
    staleness_label: str
    is_stale: bool
    detail_text: str | None
    visible: bool


@dataclass(frozen=True)
class ConditionsStripViewModel:
    tiles: tuple[ConditionsTile, ...]
    any_source_stale: bool
    rendered_at: datetime
    has_data: bool


def _aqi_severity(aqi: int | None) -> str:
    if aqi is None:
        return "neutral"
    if aqi <= 50:
        return "good"
    if aqi <= 100:
        return "moderate"
    if aqi <= 150:
        return "warning"
    return "severe"


def build_conditions_strip_view_model(
    db: Session, *, now: datetime | None = None
) -> ConditionsStripViewModel:
    now = now or datetime.now(UTC).replace(tzinfo=None)
    api = build_conditions_api_payload(db, now=now)
    tiles: list[ConditionsTile] = []
    any_stale = False

    temp = api.get("current_temp_f")
    if temp is not None:
        label = api.get("temp_staleness_label") or "Updated recently"
        stale = bool(api.get("temp_is_stale"))
        any_stale = any_stale or stale
        tiles.append(
            ConditionsTile(
                kind="temp",
                primary_value=f"{int(round(float(temp)))}°F",
                secondary_value=(
                    f"Heat index {int(round(float(api['heat_index_f'])))}°F"
                    if api.get("heat_index_f") is not None
                    else None
                ),
                attribution_chip=None,
                severity="warning" if float(temp) >= 100 else "neutral",
                staleness_label=label,
                is_stale=stale,
                detail_text=None,
                visible=True,
            )
        )

    aqi = api.get("current_aqi")
    if aqi is not None:
        param = api.get("current_aqi_parameter") or "AQI"
        station = api.get("aqi_source_station_name")
        state = api.get("aqi_source_state_code")
        dist = api.get("aqi_source_distance_mi")
        chip = None
        if station and state:
            dist_s = f" ~{int(dist)}mi south" if dist else ""
            chip = f"from {station}, {state}{dist_s}"
        label = api.get("aqi_staleness_label") or "Updated recently"
        stale = bool(api.get("aqi_is_stale"))
        any_stale = any_stale or stale
        tiles.append(
            ConditionsTile(
                kind="aqi",
                primary_value=f"AQI {aqi} ({param})",
                secondary_value=None,
                attribution_chip=chip,
                severity=_aqi_severity(int(aqi) if aqi is not None else None),
                staleness_label=label,
                is_stale=stale,
                detail_text=None,
                visible=True,
            )
        )

    alerts = api.get("active_nws_alerts") or []
    if alerts:
        first = alerts[0] if isinstance(alerts, list) else {}
        event = first.get("event") if isinstance(first, dict) else "Advisory"
        label = api.get("alerts_staleness_label") or "Updated recently"
        stale = bool(api.get("alerts_is_stale"))
        any_stale = any_stale or stale
        tiles.append(
            ConditionsTile(
                kind="advisory",
                primary_value=str(event or "Weather advisory"),
                secondary_value=f"{len(alerts)} active" if len(alerts) > 1 else None,
                attribution_chip="NWS AZZ002",
                severity="warning",
                staleness_label=label,
                is_stale=stale,
                detail_text=(
                    first.get("headline") if isinstance(first, dict) else None
                ),
                visible=True,
            )
        )

    gauge = api.get("lake_gauge_ft")
    if gauge is not None:
        label = api.get("lake_staleness_label") or "Updated recently"
        stale = bool(api.get("lake_is_stale"))
        any_stale = any_stale or stale
        tiles.append(
            ConditionsTile(
                kind="lake_level",
                primary_value=f"{float(gauge):.1f} ft",
                secondary_value="Lake gauge",
                attribution_chip="USGS 09427500",
                severity="neutral",
                staleness_label=label,
                is_stale=stale,
                detail_text=None,
                visible=True,
            )
        )

    storage = api.get("lake_storage_acft")
    if storage is not None:
        acft = float(storage)
        label = api.get("lake_staleness_label") or "Updated recently"
        stale = bool(api.get("lake_is_stale"))
        any_stale = any_stale or stale
        if acft >= 1_000_000:
            display = f"{acft / 1_000_000:.2f}M ac-ft"
        elif acft >= 1000:
            display = f"{acft / 1000:.0f}k ac-ft"
        else:
            display = f"{acft:.0f} ac-ft"
        tiles.append(
            ConditionsTile(
                kind="lake_storage",
                primary_value=display,
                secondary_value="Reservoir storage",
                attribution_chip=None,
                severity="neutral",
                staleness_label=label,
                is_stale=stale,
                detail_text=None,
                visible=True,
            )
        )

    return ConditionsStripViewModel(
        tiles=tuple(tiles),
        any_source_stale=any_stale,
        rendered_at=now,
        has_data=bool(tiles),
    )
