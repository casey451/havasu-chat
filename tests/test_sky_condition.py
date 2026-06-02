"""Sky/condition chip tests — NWS forecast shortForecast -> utility strip.

Covers the end-to-end shape (NWS forecast cache row -> api_payload ->
view_model) for the sky-condition signal, plus the nws.py surfacing of the
first/current period's shortForecast. No live API calls — the NWS fetch is
exercised against a mocked SourceLimiter and the downstream layers read a
seeded cache row. UV index is intentionally OUT of scope (it requires the
paid Open-UV external API).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from app.conditions import nws
from app.conditions.constants import SOURCE_NWS_FORECAST


def _seed_forecast_cache(db, payload: dict, *, now) -> None:
    """Upsert an NWS-forecast cache row + invalidate the in-process local cache
    so the next read_source() actually hits the DB row."""
    from app.conditions.cache import invalidate_local_cache, upsert_source

    upsert_source(db, SOURCE_NWS_FORECAST, payload, now=now)
    db.commit()
    invalidate_local_cache(SOURCE_NWS_FORECAST)


# ----- nws.py surfacing of short_forecast --------------------------------


def test_fetch_nws_forecast_surfaces_short_forecast() -> None:
    """fetch_nws_forecast_daily returns the first period's shortForecast under
    the new 'short_forecast' key (e.g. 'Sunny')."""

    def fake_get(path: str, *, timeout: float = 10.0) -> dict:
        if path.startswith("/points/"):
            return {"properties": {"forecast": "https://api.weather.gov/forecast"}}
        return {
            "properties": {
                "periods": [
                    {"temperature": 104, "shortForecast": "Sunny"},
                    {"temperature": 78, "shortForecast": "Clear"},
                ]
            }
        }

    with patch.object(nws, "_get", side_effect=fake_get):
        data = nws.fetch_nws_forecast_daily()

    assert data["short_forecast"] == "Sunny"
    assert data["forecast_high_f"] == 104.0


def test_fetch_nws_forecast_short_forecast_none_when_absent() -> None:
    """When no shortForecast is present on the first period, short_forecast is
    None and the fetcher degrades gracefully."""

    def fake_get(path: str, *, timeout: float = 10.0) -> dict:
        if path.startswith("/points/"):
            return {"properties": {"forecast": "https://api.weather.gov/forecast"}}
        return {"properties": {"periods": [{"temperature": 100}]}}

    with patch.object(nws, "_get", side_effect=fake_get):
        data = nws.fetch_nws_forecast_daily()

    assert data["short_forecast"] is None


# ----- api_payload wiring ------------------------------------------------


def test_api_payload_emits_sky_condition_when_present() -> None:
    """When the NWS-forecast cache row carries a short_forecast, the api payload
    surfaces sky_condition + sky_updated_at_iso / sky_staleness_label /
    sky_is_stale."""
    from app.conditions.api_payload import build_conditions_api_payload
    from app.db.database import SessionLocal

    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        _seed_forecast_cache(
            db,
            {"periods": [], "forecast_high_f": 104.0, "short_forecast": "Mostly Sunny"},
            now=now,
        )
        payload = build_conditions_api_payload(db, now=now)

    assert payload["sky_condition"] == "Mostly Sunny"
    assert "sky_updated_at_iso" in payload
    assert "sky_staleness_label" in payload
    assert payload["sky_is_stale"] is False


def test_api_payload_omits_sky_condition_when_absent() -> None:
    """When the cache row has no short_forecast, no sky_* fields are emitted."""
    from app.conditions.api_payload import build_conditions_api_payload
    from app.db.database import SessionLocal

    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        _seed_forecast_cache(
            db,
            {"periods": [], "forecast_high_f": 100.0, "short_forecast": None},
            now=now,
        )
        payload = build_conditions_api_payload(db, now=now)

    assert "sky_condition" not in payload
    assert "sky_updated_at_iso" not in payload
    assert "sky_staleness_label" not in payload
    assert "sky_is_stale" not in payload


# ----- view_model tile ---------------------------------------------------


def test_view_model_renders_sky_condition_tile_when_present() -> None:
    """When sky_condition is present in the api payload, the view model emits a
    kind=sky_condition tile carrying the forecast text."""
    from app.conditions.view_model import build_conditions_strip_view_model
    from app.db.database import SessionLocal

    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        _seed_forecast_cache(
            db,
            {"periods": [], "forecast_high_f": 104.0, "short_forecast": "Sunny"},
            now=now,
        )
        vm = build_conditions_strip_view_model(db, now=now)

    sky_tiles = [t for t in vm.tiles if t.kind == "sky_condition"]
    assert len(sky_tiles) == 1
    tile = sky_tiles[0]
    assert tile.primary_value == "Sunny"
    assert tile.attribution_chip == "NWS forecast"
    assert tile.severity == "neutral"
    assert tile.visible is True


def test_view_model_skips_sky_condition_tile_when_absent() -> None:
    """When sky_condition is absent, the view model omits the tile (graceful
    degradation)."""
    from app.conditions.view_model import build_conditions_strip_view_model
    from app.db.database import SessionLocal

    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        _seed_forecast_cache(
            db,
            {"periods": [], "forecast_high_f": 100.0, "short_forecast": None},
            now=now,
        )
        vm = build_conditions_strip_view_model(db, now=now)

    assert [t for t in vm.tiles if t.kind == "sky_condition"] == []


# ----- router utility tile map -------------------------------------------


def test_router_utility_tile_map_has_sky_condition() -> None:
    """The home router's _UTILITY_TILE_MAP includes a sky_condition entry with
    an icon + 'Sky' label so the utility strip can decorate the chip."""
    from app.home import router

    assert "sky_condition" in router._UTILITY_TILE_MAP
    # This repo's map is keyed kind -> (chip_kind, icon, label).
    chip_kind, icon, label = router._UTILITY_TILE_MAP["sky_condition"]
    assert label == "Sky"
    assert icon
    assert chip_kind == "sky"
