"""Assemble the "Today in Havasu" Lake Light payload (Lane A1).

Pure assembly over the EXISTING conditions cache (``app.conditions.cache``) and
the already-assembled ``build_conditions_api_payload``. No new data sources, no
HTTP. Every field carries an honest ``available``/``unavailable`` shape: when a
source is missing or stale we emit ``available=False`` with a human label rather
than fabricating a value.

The payload groups the Lake Light strip signals the /today surface renders:
lake level + water temp, wind, AQI, sunset, and the single cheapest gas station.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.conditions.api_payload import build_conditions_api_payload
from app.conditions.cache import read_source
from app.conditions.constants import SOURCE_GAS
from app.conditions.staleness import staleness_label

_UNAVAILABLE = "Unavailable"


@dataclass(frozen=True)
class TodayField:
    """One Lake Light signal with an honest availability flag.

    ``available`` is False when the underlying source is missing OR stale; in
    that case ``primary`` carries the honest "Unavailable" copy and callers
    should not present ``primary`` as a current reading.
    """

    key: str
    label: str
    primary: str
    secondary: str | None
    attribution: str | None
    is_stale: bool
    available: bool
    staleness_label: str | None


def _field(
    key: str,
    label: str,
    primary: str | None,
    *,
    secondary: str | None = None,
    attribution: str | None = None,
    is_stale: bool = False,
    staleness_label: str | None = None,
) -> TodayField:
    available = primary is not None and not is_stale
    return TodayField(
        key=key,
        label=label,
        primary=primary if available else _UNAVAILABLE,
        secondary=secondary if available else None,
        attribution=attribution,
        is_stale=bool(is_stale),
        available=available,
        staleness_label=staleness_label,
    )


def _cheapest_gas(db: Session, *, now: datetime) -> TodayField:
    """Surface the single cheapest regular-grade gas station from SOURCE_GAS.

    The gas payload (written by scripts/gas_prices_pull.py) carries a
    ``cheapest`` list of stations, each with ``name``/``brand``/``prices`` and an
    optional ``provider_slug``. We pick the first entry with a regular price.
    """
    row = read_source(db, SOURCE_GAS, now=now)
    if row is None or not isinstance(row.data, dict):
        return _field("cheapest_gas", "Cheapest gas", None)
    label, stale = staleness_label(row.fetched_at, now)
    is_stale = bool(stale or row.is_stale)
    cheapest = row.data.get("cheapest")
    station: dict[str, Any] | None = None
    price: Any = None
    if isinstance(cheapest, list):
        for entry in cheapest:
            if not isinstance(entry, dict):
                continue
            prices = entry.get("prices")
            if isinstance(prices, dict) and prices.get("regular"):
                station = entry
                price = prices.get("regular")
                break
    if station is None or price is None:
        return _field("cheapest_gas", "Cheapest gas", None, staleness_label=label)
    name = station.get("name") or "Station"
    brand = station.get("brand")
    secondary = f"{brand} · {name}" if brand else str(name)
    return _field(
        "cheapest_gas",
        "Cheapest gas",
        f"${price}",
        secondary=secondary,
        attribution="GasBuddy / Google",
        is_stale=is_stale,
        staleness_label=label,
    )


def build_today_payload(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """Return the assembled "Today in Havasu" payload as a plain dict.

    Reuses ``build_conditions_api_payload`` for the weather/lake/AQI/sunset
    signals (so staleness + gating logic stays single-sourced) and reads the gas
    cache directly for the cheapest-station surfacing.
    """
    now = now or datetime.now(UTC).replace(tzinfo=None)
    api = build_conditions_api_payload(db, now=now)

    fields: list[TodayField] = []

    # Lake level (USGS 09427500).
    gauge = api.get("lake_gauge_ft")
    fields.append(
        _field(
            "lake_level",
            "Lake level",
            f"{float(gauge):.1f} ft" if gauge is not None else None,
            secondary="Lake gauge",
            attribution="USGS 09427500",
            is_stale=bool(api.get("lake_is_stale")),
            staleness_label=api.get("lake_staleness_label"),
        )
    )

    # Water temperature (USGS 09426630, feature-gated upstream).
    water_temp_f = api.get("water_temp_f")
    fields.append(
        _field(
            "water_temp",
            "Water temp",
            f"{float(water_temp_f):.0f}°F" if water_temp_f is not None else None,
            attribution="USGS 09426630",
            is_stale=bool(api.get("water_temp_is_stale")),
            staleness_label=api.get("water_temp_staleness_label"),
        )
    )

    # Wind (NWS current observation). When the observation carries a direction
    # bearing we prefix the compass label (e.g. "NW 8 mph"); when it is absent we
    # gracefully show speed alone ("8 mph").
    wind = api.get("wind_speed_mph")
    wind_cardinal = api.get("wind_direction_cardinal")
    if wind is None:
        wind_primary = None
    elif isinstance(wind_cardinal, str) and wind_cardinal:
        wind_primary = f"{wind_cardinal} {float(wind):.0f} mph"
    else:
        wind_primary = f"{float(wind):.0f} mph"
    fields.append(
        _field(
            "wind",
            "Wind",
            wind_primary,
            attribution="NWS",
            is_stale=bool(api.get("temp_is_stale")),
            staleness_label=api.get("temp_staleness_label"),
        )
    )

    # Air quality (AirNow).
    aqi = api.get("current_aqi")
    param = api.get("current_aqi_parameter")
    fields.append(
        _field(
            "aqi",
            "Air quality",
            f"AQI {aqi}" if aqi is not None else None,
            secondary=str(param) if param else None,
            attribution="AirNow",
            is_stale=bool(api.get("aqi_is_stale")),
            staleness_label=api.get("aqi_staleness_label"),
        )
    )

    # Sunset (NWS, approximated from the evening forecast period).
    sunset_local = api.get("sunset_local")
    fields.append(
        _field(
            "sunset",
            "Sunset",
            str(sunset_local) if isinstance(sunset_local, str) and sunset_local.strip() else None,
            attribution="NWS forecast",
            is_stale=bool(api.get("sunset_is_stale")),
            staleness_label=api.get("sunset_staleness_label"),
        )
    )

    # Cheapest gas (SOURCE_GAS).
    fields.append(_cheapest_gas(db, now=now))

    return {
        "rendered_at_iso": api.get("rendered_at_iso"),
        "fields": fields,
        "any_available": any(f.available for f in fields),
    }
