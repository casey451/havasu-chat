"""V1.5 wave 3 -- USGS water-temperature fetcher tests (USGS station 09426630).

Covers the feature-flag default-OFF behavior, the -100000 sentinel filtering,
the Celsius -> Fahrenheit conversion, and the latest-continuous OGC URL path
(mirrors the Phase 8a.2 lesson from test_phase8_fetcher_usgs.py).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.conditions import usgs_water_temp


@pytest.fixture(autouse=True)
def _reset_feature_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure each test starts with the flag explicitly unset, so any test that
    relies on the default-OFF behavior is not polluted by env from a prior test."""
    monkeypatch.delenv(usgs_water_temp.FEATURE_FLAG_ENV_VAR, raising=False)


def test_feature_disabled_by_default() -> None:
    assert usgs_water_temp.feature_enabled() is False


@pytest.mark.parametrize("value", ["true", "TRUE", "True", "1", "yes", "on"])
def test_feature_enabled_when_env_set_truthy(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(usgs_water_temp.FEATURE_FLAG_ENV_VAR, value)
    assert usgs_water_temp.feature_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "", "anything-else"])
def test_feature_disabled_when_env_set_falsy(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(usgs_water_temp.FEATURE_FLAG_ENV_VAR, value)
    assert usgs_water_temp.feature_enabled() is False


def test_fetch_returns_empty_when_feature_disabled_makes_no_http_call() -> None:
    """When the flag is OFF, the fetcher must NOT touch httpx + must return an
    empty payload with feature_enabled=False. This is the prod-safe default."""
    with patch.object(usgs_water_temp.httpx, "Client") as mock_client:
        data = usgs_water_temp.fetch_usgs_water_temp_09426630()
    assert data["water_temp_c"] is None
    assert data["water_temp_f"] is None
    assert data["observed_at"] is None
    assert data["feature_enabled"] is False
    assert data["history"] == []
    assert data["site"] == "09426630"
    mock_client.assert_not_called()


def test_fetch_parses_normal_reading_and_converts_to_fahrenheit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(usgs_water_temp.FEATURE_FLAG_ENV_VAR, "true")

    def fake_retry(fn):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "features": [
                {
                    "properties": {
                        "value": 22.5,  # 22.5 C
                        "time": "2026-05-23T18:00:00+00:00",
                    }
                }
            ]
        }
        fn()
        return resp

    with patch.object(
        usgs_water_temp._USGS_LIMITER, "call_with_retry", side_effect=fake_retry
    ):
        data = usgs_water_temp.fetch_usgs_water_temp_09426630()

    assert data["water_temp_c"] == 22.5
    # 22.5 C = 72.5 F
    assert data["water_temp_f"] == pytest.approx(72.5, abs=0.01)
    assert data["observed_at"] == "2026-05-23T18:00:00+00:00"
    assert data["feature_enabled"] is True
    assert len(data["history"]) == 1
    assert data["history"][0]["is_sentinel"] is False
    assert data["history"][0]["parameter_code"] == "00010"


def test_fetch_filters_minus_100000_sentinel_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the gage is malfunctioning USGS returns value=-100000 as the
    missing-data placeholder. Fetcher must report water_temp_c/_f as None but
    still emit the history entry with is_sentinel=True for audit visibility."""
    monkeypatch.setenv(usgs_water_temp.FEATURE_FLAG_ENV_VAR, "true")

    def fake_retry(fn):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "features": [
                {
                    "properties": {
                        "value": "-100000",  # sentinel as string (matches USGS new payload shape)
                        "time": "2026-05-21T17:00:00+00:00",
                    }
                }
            ]
        }
        fn()
        return resp

    with patch.object(
        usgs_water_temp._USGS_LIMITER, "call_with_retry", side_effect=fake_retry
    ):
        data = usgs_water_temp.fetch_usgs_water_temp_09426630()

    assert data["water_temp_c"] is None
    assert data["water_temp_f"] is None
    assert data["observed_at"] is None  # no non-sentinel reading found
    assert data["feature_enabled"] is True
    assert len(data["history"]) == 1
    assert data["history"][0]["is_sentinel"] is True
    assert data["history"][0]["value"] is None  # sentinel masked to None


def test_fetch_picks_first_non_sentinel_when_history_has_mix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the response contains a mix of sentinel + real readings, fetcher
    reports the first non-sentinel value as the canonical reading."""
    monkeypatch.setenv(usgs_water_temp.FEATURE_FLAG_ENV_VAR, "true")

    def fake_retry(fn):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "features": [
                {
                    "properties": {
                        "value": "-100000",
                        "time": "2026-05-23T17:00:00+00:00",
                    }
                },
                {
                    "properties": {
                        "value": "20.0",  # 20 C = 68 F
                        "time": "2026-05-23T16:45:00+00:00",
                    }
                },
            ]
        }
        fn()
        return resp

    with patch.object(
        usgs_water_temp._USGS_LIMITER, "call_with_retry", side_effect=fake_retry
    ):
        data = usgs_water_temp.fetch_usgs_water_temp_09426630()

    # water_temp_c picks the first non-sentinel value (20.0 C); sentinel entry
    # is still in history for audit.
    assert data["water_temp_c"] == 20.0
    assert data["water_temp_f"] == pytest.approx(68.0, abs=0.01)
    assert data["observed_at"] == "2026-05-23T16:45:00+00:00"
    assert len(data["history"]) == 2
    assert data["history"][0]["is_sentinel"] is True
    assert data["history"][1]["is_sentinel"] is False


def test_fetch_uses_latest_continuous_collection_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 8a.2 lesson carry: the URL path must point at the renamed
    latest-continuous collection. The legacy observations path returns 404."""
    monkeypatch.setenv(usgs_water_temp.FEATURE_FLAG_ENV_VAR, "true")
    captured_urls: list[str] = []
    captured_params: list[dict] = []

    def fake_retry(fn):
        fn()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"features": []}
        return resp

    class _FakeClient:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def __enter__(self) -> "_FakeClient":
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, url: str, **kwargs):
            captured_urls.append(url)
            captured_params.append(kwargs.get("params") or {})
            return MagicMock()

    with patch.object(usgs_water_temp.httpx, "Client", _FakeClient):
        with patch.object(
            usgs_water_temp._USGS_LIMITER, "call_with_retry", side_effect=fake_retry
        ):
            usgs_water_temp.fetch_usgs_water_temp_09426630()

    assert captured_urls, "fetcher did not issue any HTTP requests"
    for url in captured_urls:
        assert "/collections/latest-continuous/items" in url, (
            f"URL still pointing at deprecated path: {url}"
        )
        assert "/collections/observations/items" not in url, (
            f"URL still pointing at deprecated 'observations' collection: {url}"
        )
    assert captured_params, "fetcher did not pass any params"
    for params in captured_params:
        assert params.get("monitoring_location_id") == "USGS-09426630", (
            f"params did not include the 09426630 station id: {params}"
        )
        assert params.get("parameter_code") == "00010", (
            f"params did not request water-temperature parameter (00010): {params}"
        )


def test_site_overridable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(usgs_water_temp.FEATURE_FLAG_ENV_VAR, "true")
    monkeypatch.setenv("USGS_WATER_TEMP_SITE", "09427520")

    def fake_retry(fn):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"features": []}
        fn()
        return resp

    with patch.object(
        usgs_water_temp._USGS_LIMITER, "call_with_retry", side_effect=fake_retry
    ):
        data = usgs_water_temp.fetch_usgs_water_temp_09426630()

    assert data["site"] == "09427520"


def test_constant_added_to_constants_module() -> None:
    """Smoke: the SOURCE_USGS_WATER_TEMP constant exists in constants.py for
    eventual SOURCE_KEYS / TTL_BY_SOURCE wiring."""
    from app.conditions import constants

    assert constants.SOURCE_USGS_WATER_TEMP == "usgs_water_temp_09426630"
    # NOT yet in SOURCE_KEYS (deferred wiring per module docstring).
    assert constants.SOURCE_USGS_WATER_TEMP not in constants.SOURCE_KEYS
    assert constants.SOURCE_USGS_WATER_TEMP not in constants.TTL_BY_SOURCE
