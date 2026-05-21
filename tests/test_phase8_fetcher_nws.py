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


def test_fetch_nws_current_extracts_temp() -> None:
    points = {"properties": {"observationStations": "https://api.weather.gov/stations"}}
    stations = {"features": [{"id": "https://api.weather.gov/stations/KHII"}]}
    obs = {
        "properties": {
            "temperature": {"value": 37.0},
            "heatIndex": {"value": None},
            "windSpeed": {"value": 5.0},
            "windDirection": {"value": 180},
        }
    }

    with patch("app.conditions.nws._get", side_effect=[points, stations, obs]):
        data = nws.fetch_nws_current()

    assert data["temperature_f"] is not None
    assert data["temperature_f"] > 90
