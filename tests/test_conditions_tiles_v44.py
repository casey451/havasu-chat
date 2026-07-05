"""v4.4 PR-4 — conditions strip: Temp · Water · Wind · UV · Sunset · Gas.

Clouds retired (the pipeline only had the NWS sky *word*, never a real cloud %).
Water + Sunset added, both honest (measured gage / computed astronomical). Each
tile is honest-omit; no "N/A" placeholders.
"""

from __future__ import annotations

from unittest.mock import patch

from app.home import redesign

_GAS_EMPTY = {"cheapest": [], "is_stale": False, "staleness_label": None}
_GAS = {
    "cheapest": [{"price": "$3.79", "name": "Circle K", "cross_street": "Hwy 95",
                  "directions_url": "https://maps"}],
    "is_stale": False, "staleness_label": "Updated 1h ago",
}


def _full_payload() -> dict:
    return {
        "current_temp_f": 101, "temp_is_stale": False,
        "wind_speed_mph": 8,
        "uv_index": 9, "uv_is_stale": False,
        "water_temp_f": 72, "water_temp_is_stale": False,
        "sunset_local": "7:42 PM", "sunset_is_stale": False,
        # sky_condition is still emitted by the api payload but MUST be ignored now:
        "sky_condition": "Mostly Cloudy",
    }


def _tiles(payload: dict, gas: dict) -> list[dict]:
    with (
        patch("app.home.redesign.build_conditions_api_payload", return_value=payload),
        patch("app.home.redesign.gas_top5", return_value=gas),
    ):
        return redesign.conditions_tiles(None)  # type: ignore[arg-type]


def test_order_and_no_clouds() -> None:
    tiles = _tiles(_full_payload(), _GAS)
    keys = [t["key"] for t in tiles]
    assert keys == ["temp", "water_temp", "wind", "uv", "sunset", "gas"]
    assert "clouds" not in keys


def test_sunset_value_and_unit_split() -> None:
    sunset = next(t for t in _tiles(_full_payload(), _GAS_EMPTY) if t["key"] == "sunset")
    assert sunset["value"] == "7:42"
    assert sunset["unit"] == "pm"
    assert sunset["icon"] == "sunset"


def test_water_tile_marked_and_omitted_when_absent() -> None:
    water = next(t for t in _tiles(_full_payload(), _GAS_EMPTY) if t["key"] == "water_temp")
    assert water["is_water"] is True
    assert water["label"] == "Water"
    # Honest omission: no water reading -> no water tile (and never a placeholder).
    p = _full_payload()
    del p["water_temp_f"]
    keys = [t["key"] for t in _tiles(p, _GAS_EMPTY)]
    assert "water_temp" not in keys


def test_sunset_omitted_when_absent_no_placeholder() -> None:
    p = _full_payload()
    del p["sunset_local"]
    tiles = _tiles(p, _GAS_EMPTY)
    assert all(t["key"] != "sunset" for t in tiles)
    assert all(t["value"] not in ("", "N/A", "—") for t in tiles)


def test_conditions_provenance_source_urls() -> None:
    # v4.7: every measured tile links to where its number comes from — temp + wind
    # to the NWS KHII observation page, water to the USBR RISE Parker Dam item, UV
    # to the EPA page. Sunset (astronomically computed) has NO source page, so it
    # stays unlinked — an honest omission, not a fabricated link.
    from app.conditions.constants import (
        SOURCE_PAGE_NWS_KHII,
        SOURCE_PAGE_RISE_WATER_TEMP,
        SOURCE_PAGE_UV,
    )

    by_key = {t["key"]: t for t in _tiles(_full_payload(), _GAS_EMPTY)}
    assert by_key["temp"]["source_url"] == SOURCE_PAGE_NWS_KHII
    assert by_key["wind"]["source_url"] == SOURCE_PAGE_NWS_KHII
    assert by_key["water_temp"]["source_url"] == SOURCE_PAGE_RISE_WATER_TEMP
    assert by_key["uv"]["source_url"] == SOURCE_PAGE_UV
    # Water is a genuinely different source from temp/wind (RISE, not NWS).
    assert by_key["water_temp"]["source_url"] != by_key["temp"]["source_url"]
    # Sunset is computed → no external source page → unlinked.
    assert "source_url" not in by_key["sunset"]
