"""Lane A1 — "Today in Havasu" payload + sunset assembly + /today route."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.conditions.api_payload import build_conditions_api_payload, degrees_to_cardinal
from app.conditions.cache import invalidate_local_cache, upsert_source
from app.conditions.constants import (
    SOURCE_AIRNOW,
    SOURCE_GAS,
    SOURCE_NWS_CURRENT,
    SOURCE_NWS_SUNSET,
    SOURCE_USGS,
)
from app.conditions.today_payload import build_today_payload
from app.db.database import SessionLocal
from app.main import app


def _field(payload: dict, key: str):
    return next(f for f in payload["fields"] if f.key == key)


@pytest.fixture(autouse=True)
def _clear_cache():
    invalidate_local_cache()
    yield
    invalidate_local_cache()


def _seed_fresh(now: datetime) -> None:
    with SessionLocal() as db:
        upsert_source(db, SOURCE_USGS, {"lake_gauge_ft": 449.2, "lake_storage_acft": 619000}, now=now)
        upsert_source(db, SOURCE_NWS_CURRENT, {"temperature_f": 101.0, "wind_speed_mph": 8.4}, now=now)
        upsert_source(
            db,
            SOURCE_AIRNOW,
            {"current_aqi": 42, "current_aqi_parameter": "O3"},
            now=now,
        )
        upsert_source(
            db,
            SOURCE_NWS_SUNSET,
            {"sunset_iso": "2026-06-02T19:42:00-07:00", "periods": []},
            now=now,
        )
        upsert_source(
            db,
            SOURCE_GAS,
            {
                "cheapest": [
                    {"name": "Speedy", "brand": "Arco", "prices": {"regular": "3.79"}},
                ]
            },
            now=now,
        )
        db.commit()


def test_today_payload_all_fields_available_when_fresh() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    _seed_fresh(now)
    invalidate_local_cache()
    with SessionLocal() as db:
        payload = build_today_payload(db, now=now)

    keys = {f.key for f in payload["fields"]}
    assert {"lake_level", "water_temp", "wind", "aqi", "sunset", "cheapest_gas"} <= keys
    assert payload["any_available"] is True

    assert _field(payload, "lake_level").available is True
    assert _field(payload, "lake_level").primary == "449.2 ft"
    assert _field(payload, "wind").primary == "8 mph"
    assert _field(payload, "aqi").primary == "AQI 42"
    gas = _field(payload, "cheapest_gas")
    assert gas.available is True
    assert gas.primary == "$3.79"
    assert "Arco" in (gas.secondary or "")


def test_today_payload_gas_secondary_not_duplicated_when_brand_equals_name() -> None:
    """When GasBuddy repeats the brand as the name, don't render it twice
    ("Love's Travel Stop · Love's Travel Stop") — site review §4b."""
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        upsert_source(
            db,
            SOURCE_GAS,
            {
                "cheapest": [
                    {
                        "name": "Love's Travel Stop",
                        "brand": "love's travel stop",
                        "prices": {"regular": "3.49"},
                    },
                ]
            },
            now=now,
        )
        db.commit()
    invalidate_local_cache()
    with SessionLocal() as db:
        payload = build_today_payload(db, now=now)

    gas = _field(payload, "cheapest_gas")
    assert gas.secondary == "Love's Travel Stop"
    assert " · " not in (gas.secondary or "")


def test_today_payload_sunset_formats_local_time() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    _seed_fresh(now)
    invalidate_local_cache()
    with SessionLocal() as db:
        payload = build_today_payload(db, now=now)
    sunset = _field(payload, "sunset")
    # 19:42 at -07:00 is already America/Phoenix wall-clock -> 7:42 PM.
    assert sunset.available is True
    assert sunset.primary == "7:42 PM"


def test_today_payload_stale_source_is_unavailable() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    # Lake gauge fetched 5h ago -> staleness_label flags stale (>=2h).
    old = now - timedelta(hours=5)
    with SessionLocal() as db:
        upsert_source(db, SOURCE_USGS, {"lake_gauge_ft": 449.2}, now=old)
        db.commit()
    invalidate_local_cache()
    with SessionLocal() as db:
        payload = build_today_payload(db, now=now)
    lake = _field(payload, "lake_level")
    assert lake.available is False
    assert lake.primary == "Unavailable"
    assert lake.is_stale is True


def test_today_payload_missing_source_is_unavailable() -> None:
    # No seeding at all -> every field unavailable, any_available False.
    invalidate_local_cache()
    now = datetime(2999, 1, 1)  # far future so any stray rows read as stale anyway
    with SessionLocal() as db:
        payload = build_today_payload(db, now=now)
    assert payload["any_available"] is False
    assert all(f.primary == "Unavailable" for f in payload["fields"])


def test_api_payload_surfaces_sunset_local() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        upsert_source(
            db,
            SOURCE_NWS_SUNSET,
            {"sunset_iso": "2026-06-02T02:42:00Z", "periods": []},
            now=now,
        )
        db.commit()
    invalidate_local_cache()
    with SessionLocal() as db:
        api = build_conditions_api_payload(db, now=now)
    assert api.get("sunset_iso") == "2026-06-02T02:42:00Z"
    # 02:42 UTC -> 19:42 previous day America/Phoenix -> 7:42 PM.
    assert api.get("sunset_local") == "7:42 PM"


@pytest.mark.parametrize(
    "deg,expected",
    [
        (0, "N"),
        (90, "E"),
        (180, "S"),
        (270, "W"),
        (315, "NW"),
        (45, "NE"),
        (22.5, "NNE"),
        (360, "N"),
        (-45, "NW"),
        (359, "N"),
        (None, None),
    ],
)
def test_degrees_to_cardinal_boundaries(deg, expected) -> None:
    assert degrees_to_cardinal(deg) == expected


def test_degrees_to_cardinal_rejects_non_numbers() -> None:
    assert degrees_to_cardinal("nw") is None
    assert degrees_to_cardinal(True) is None
    assert degrees_to_cardinal(float("nan")) is None


def test_api_payload_emits_wind_direction_when_present() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        upsert_source(
            db,
            SOURCE_NWS_CURRENT,
            {"temperature_f": 100.0, "wind_speed_mph": 8.4, "wind_direction_deg": 315},
            now=now,
        )
        db.commit()
    invalidate_local_cache()
    with SessionLocal() as db:
        api = build_conditions_api_payload(db, now=now)
    assert api.get("wind_direction_deg") == 315
    assert api.get("wind_direction_cardinal") == "NW"


def test_api_payload_wind_direction_null_when_absent() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        upsert_source(
            db,
            SOURCE_NWS_CURRENT,
            {"temperature_f": 100.0, "wind_speed_mph": 8.4},
            now=now,
        )
        db.commit()
    invalidate_local_cache()
    with SessionLocal() as db:
        api = build_conditions_api_payload(db, now=now)
    # Field present (key always emitted in the nws_current block) but null,
    # so /api/conditions stays backward-compatible.
    assert "wind_speed_mph" in api
    assert api.get("wind_direction_deg") is None
    assert api.get("wind_direction_cardinal") is None


def test_today_payload_wind_includes_direction() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        upsert_source(
            db,
            SOURCE_NWS_CURRENT,
            {"temperature_f": 100.0, "wind_speed_mph": 8.4, "wind_direction_deg": 315},
            now=now,
        )
        db.commit()
    invalidate_local_cache()
    with SessionLocal() as db:
        payload = build_today_payload(db, now=now)
    wind = _field(payload, "wind")
    assert wind.available is True
    assert wind.primary == "NW 8 mph"


def test_today_payload_wind_speed_only_when_direction_absent() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        upsert_source(
            db,
            SOURCE_NWS_CURRENT,
            {"temperature_f": 100.0, "wind_speed_mph": 8.4},
            now=now,
        )
        db.commit()
    invalidate_local_cache()
    with SessionLocal() as db:
        payload = build_today_payload(db, now=now)
    wind = _field(payload, "wind")
    assert wind.available is True
    assert wind.primary == "8 mph"


def test_today_route_renders_strip() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    _seed_fresh(now)
    invalidate_local_cache()
    client = TestClient(app)
    r = client.get("/today")
    assert r.status_code == 200
    assert "Today in Havasu" in r.text
    assert "Lake level" in r.text
