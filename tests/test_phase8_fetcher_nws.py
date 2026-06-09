"""Phase 8a — NWS fetchers (mocked)."""

from __future__ import annotations

from unittest.mock import patch

from app.conditions import nws


def test_fetch_nws_alerts_parses_features() -> None:
    payload = {
        "features": [
            {
                "properties": {
                    "event": "Heat Advisory",
                    "headline": "Heat Advisory for Lake Havasu",
                }
            }
        ]
    }

    with patch("app.conditions.nws._get", return_value=payload):
        data = nws.fetch_nws_alerts_lhc_zone()

    assert len(data["alerts"]) == 1
    assert data["alerts"][0]["event"] == "Heat Advisory"


_PRIMARY_PATH = f"/stations/{nws.LHC_PRIMARY_STATION}/observations/latest"


def test_fetch_nws_current_prefers_khii_when_obs_carries_temp() -> None:
    """KHII (the pinned official LHC station) is the primary source: when its
    latest obs carries a temperature, it is used and the points/stations walk
    is never reached."""
    khii_obs = {
        "properties": {
            "temperature": {"value": 37.0},
            "heatIndex": {"value": None},
            "windSpeed": {"value": 5.0},
            "windDirection": {"value": 180},
        }
    }

    def fake_get(path: str):
        if path == _PRIMARY_PATH:
            return khii_obs
        raise AssertionError(f"walk should not run; unexpected call: {path}")

    with patch("app.conditions.nws._get", side_effect=fake_get):
        data = nws.fetch_nws_current()

    assert data["temperature_f"] is not None
    assert data["temperature_f"] > 90  # 37C → 98.6F
    assert data["wind_direction_deg"] == 180


def test_fetch_nws_current_falls_back_to_walk_when_khii_temp_null() -> None:
    """When KHII's latest obs has no temperature, fall through to the
    nearest-station walk and keep the first reading that carries one."""
    points = {"properties": {"observationStations": "https://api.weather.gov/stations"}}
    stations = {
        "features": [
            {"id": "https://api.weather.gov/stations/KNULL"},
            {"id": "https://api.weather.gov/stations/KOTHER"},
        ]
    }
    khii_null = {
        "properties": {
            "temperature": {"value": None},
            "windSpeed": {"value": 1.0},
            "windDirection": {"value": 10},
        }
    }
    obs_null = {
        "properties": {
            "temperature": {"value": None},
            "heatIndex": {"value": None},
            "windSpeed": {"value": 5.0},
            "windDirection": {"value": 180},
        }
    }
    obs_real = {
        "properties": {
            "temperature": {"value": 30.0},
            "heatIndex": {"value": None},
            "windSpeed": {"value": 3.0},
            "windDirection": {"value": 90},
        }
    }

    def fake_get(path: str):
        if path == _PRIMARY_PATH:
            return khii_null
        if "/points/" in path:
            return points
        if path.endswith("/stations"):
            return stations
        if "KNULL" in path:
            return obs_null
        if "KOTHER" in path:
            return obs_real
        raise AssertionError(path)

    with patch("app.conditions.nws._get", side_effect=fake_get):
        data = nws.fetch_nws_current()

    assert data["temperature_f"] == 86.0  # 30C from the second walk station


def test_fetch_nws_current_keeps_first_obs_when_all_temps_null() -> None:
    """All-null temps: temperature stays None but wind still surfaces from the
    nearest station's observation."""
    points = {"properties": {"observationStations": "https://api.weather.gov/stations"}}
    stations = {"features": [{"id": "https://api.weather.gov/stations/KNULL"}]}
    obs_null = {
        "properties": {
            "temperature": {"value": None},
            "heatIndex": {"value": None},
            "windSpeed": {"value": 5.0},
            "windDirection": {"value": 180},
        }
    }

    def fake_get(path: str):
        if "/points/" in path:
            return points
        if path.endswith("/stations"):
            return stations
        return obs_null

    with patch("app.conditions.nws._get", side_effect=fake_get):
        data = nws.fetch_nws_current()

    assert data["temperature_f"] is None
    assert data["wind_direction_deg"] == 180
