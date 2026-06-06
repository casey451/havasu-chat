"""Wind tile replaces the lake-level tile in the home utility strip.

On a desert lake the live wind reading is the higher-value boating/paddling
signal than the slow-moving reservoir gauge, so the home strip now shows Wind
where it used to show Lake level. Lake level remains on /today and in the JSON
conditions payload — only the home utility strip changed.
"""

from __future__ import annotations

from unittest.mock import patch

from app.conditions import view_model as vm_mod
from app.db.database import SessionLocal


def test_view_model_emits_wind_tile_with_cardinal() -> None:
    payload = {"wind_speed_mph": 12.4, "wind_direction_cardinal": "SW"}
    with patch.object(vm_mod, "build_conditions_api_payload", return_value=payload):
        with SessionLocal() as db:
            vm = vm_mod.build_conditions_strip_view_model(db)
    wind = [t for t in vm.tiles if t.kind == "wind"]
    assert len(wind) == 1
    assert wind[0].primary_value == "12 mph"
    assert "SW" in (wind[0].secondary_value or "")


def test_view_model_wind_tile_omitted_without_data() -> None:
    with patch.object(vm_mod, "build_conditions_api_payload", return_value={}):
        with SessionLocal() as db:
            vm = vm_mod.build_conditions_strip_view_model(db)
    assert [t for t in vm.tiles if t.kind == "wind"] == []


def test_view_model_wind_severity_flags_high_wind() -> None:
    payload = {"wind_speed_mph": 28}
    with patch.object(vm_mod, "build_conditions_api_payload", return_value=payload):
        with SessionLocal() as db:
            vm = vm_mod.build_conditions_strip_view_model(db)
    wind = [t for t in vm.tiles if t.kind == "wind"][0]
    assert wind.severity == "warning"
    assert wind.secondary_value == "Wind"


def test_home_strip_uses_wind_not_lake_level() -> None:
    from app.home import router

    assert "wind" in router._UTILITY_TILE_MAP
    assert router._UTILITY_TILE_MAP["wind"][0] == "wind"
    # Lake level no longer rendered in the home utility strip.
    assert "lake_level" not in router._UTILITY_TILE_MAP
