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
            "Distance": 60,
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


def test_fetch_airnow_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIRNOW_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="AIRNOW_API_KEY"):
        airnow.fetch_airnow_current()
