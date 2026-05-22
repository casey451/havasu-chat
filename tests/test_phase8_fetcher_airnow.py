"""Phase 8a — AirNow fetcher (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.conditions import airnow


@pytest.fixture
def airnow_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIRNOW_API_KEY", "test-key")


def test_fetch_airnow_parses_rows(airnow_env: None) -> None:
    payload = [
        {
            "AQI": 47,
            "ParameterName": "O3",
            "SiteName": "Blythe",
            "StateCode": "CA",
            "Latitude": 33.6178,
            "Longitude": -114.5885,
            "Category": {"Name": "Good"},
        }
    ]
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = payload

    with patch.object(airnow._AIRNOW_LIMITER, "call_with_retry", return_value=mock_resp):
        data = airnow.fetch_airnow_current()

    assert data["current_aqi"] == 47
    assert data["current_aqi_parameter"] == "O3"
    assert data["aqi_source_station_name"] == "Blythe"


def test_fetch_airnow_computes_distance_from_coords(airnow_env: None) -> None:
    """Blythe CA ≈ 60mi south of LHC — Haversine should produce that."""
    payload = [
        {
            "AQI": 47,
            "ParameterName": "O3",
            "SiteName": "Blythe",
            "StateCode": "CA",
            "Latitude": 33.6178,
            "Longitude": -114.5885,
            "Category": {"Name": "Good"},
        }
    ]
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = payload

    with patch.object(airnow._AIRNOW_LIMITER, "call_with_retry", return_value=mock_resp):
        data = airnow.fetch_airnow_current()

    dist = data["aqi_source_distance_mi"]
    assert dist is not None
    assert 55 <= dist <= 65, f"Expected ~60mi (Blythe→LHC); got {dist}"


def test_fetch_airnow_distance_none_when_coords_missing(airnow_env: None) -> None:
    """No Latitude/Longitude in payload → aqi_source_distance_mi is None
    (preserves the graceful-null contract that view_model.py:82-85 and
    conditions_strip.js:13 depend on)."""
    payload = [
        {
            "AQI": 47,
            "ParameterName": "O3",
            "SiteName": "Blythe",
            "StateCode": "CA",
            "Category": {"Name": "Good"},
        }
    ]
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = payload

    with patch.object(airnow._AIRNOW_LIMITER, "call_with_retry", return_value=mock_resp):
        data = airnow.fetch_airnow_current()

    assert data["aqi_source_distance_mi"] is None


def test_fetch_airnow_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIRNOW_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="AIRNOW_API_KEY"):
        airnow.fetch_airnow_current()
