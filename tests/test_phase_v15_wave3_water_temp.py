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
def test_feature_enabled_when_env_set_truthy(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(usgs_water_temp.FEATURE_FLAG_ENV_VAR, value)
    assert usgs_water_temp.feature_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "", "anything-else"])
def test_feature_disabled_when_env_set_falsy(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
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

    with patch.object(usgs_water_temp._USGS_LIMITER, "call_with_retry", side_effect=fake_retry):
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

    with patch.object(usgs_water_temp._USGS_LIMITER, "call_with_retry", side_effect=fake_retry):
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

    with patch.object(usgs_water_temp._USGS_LIMITER, "call_with_retry", side_effect=fake_retry):
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
        with patch.object(usgs_water_temp._USGS_LIMITER, "call_with_retry", side_effect=fake_retry):
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

    with patch.object(usgs_water_temp._USGS_LIMITER, "call_with_retry", side_effect=fake_retry):
        data = usgs_water_temp.fetch_usgs_water_temp_09426630()

    assert data["site"] == "09427520"


def test_constant_wired_into_source_keys_and_ttl() -> None:
    """Wave-3 wiring: SOURCE_USGS_WATER_TEMP IS registered in SOURCE_KEYS +
    TTL_BY_SOURCE (3600s, same cadence as the lake-gauge USGS source)."""
    from app.conditions import constants

    assert constants.SOURCE_USGS_WATER_TEMP == "usgs_water_temp_09426630"
    assert constants.SOURCE_USGS_WATER_TEMP in constants.SOURCE_KEYS
    assert constants.TTL_BY_SOURCE[constants.SOURCE_USGS_WATER_TEMP] == 3600


def test_fetcher_registered_in_fetcher_dispatch_dict() -> None:
    """Wave-3 wiring: fetch_usgs_water_temp_09426630 is reachable via the
    central _FETCHERS dispatch dict keyed by SOURCE_USGS_WATER_TEMP, so
    fetch_one_source(db, SOURCE_USGS_WATER_TEMP) works without raising
    ValueError('unknown conditions source: ...')."""
    from app.conditions import fetcher
    from app.conditions.constants import SOURCE_USGS_WATER_TEMP

    assert SOURCE_USGS_WATER_TEMP in fetcher._FETCHERS
    assert (
        fetcher._FETCHERS[SOURCE_USGS_WATER_TEMP] is usgs_water_temp.fetch_usgs_water_temp_09426630
    )


# ----- API payload + view-model wiring tests -----------------------------
#
# These tests exercise the end-to-end shape (cache row -> api_payload ->
# view_model) for the water-temp signal, gating purely on the cache row's
# feature_enabled flag rather than on the env var. This mirrors the prod
# data flow: the fetcher writes feature_enabled into the cache row at fetch
# time, and downstream layers honor whatever was captured there.


def _seed_water_temp_cache(db, payload: dict, *, now) -> None:
    """Helper: upsert a water-temp cache row + invalidate the in-process
    local cache so the next read_source() actually hits the DB row."""
    from app.conditions.cache import invalidate_local_cache, upsert_source
    from app.conditions.constants import SOURCE_USGS_WATER_TEMP

    upsert_source(db, SOURCE_USGS_WATER_TEMP, payload, now=now)
    db.commit()
    invalidate_local_cache(SOURCE_USGS_WATER_TEMP)


def test_api_payload_emits_water_temp_when_feature_enabled() -> None:
    """When the cache row's feature_enabled=True and the fetcher captured a
    real reading, /api/conditions exposes water_temp_c / water_temp_f /
    water_temp_updated_at_iso / water_temp_staleness_label / water_temp_is_stale."""
    from datetime import UTC, datetime

    from fastapi.testclient import TestClient

    from app.db.database import SessionLocal
    from app.main import app

    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        _seed_water_temp_cache(
            db,
            {
                "site": "09426630",
                "water_temp_c": 22.5,
                "water_temp_f": 72.5,
                "observed_at": "2026-05-23T18:00:00+00:00",
                "feature_enabled": True,
                "history": [
                    {
                        "parameter_code": "00010",
                        "value": 22.5,
                        "observed_at": "2026-05-23T18:00:00+00:00",
                        "is_sentinel": False,
                    }
                ],
            },
            now=now,
        )

    client = TestClient(app)
    r = client.get("/api/conditions")
    assert r.status_code == 200
    body = r.json()
    assert body["water_temp_c"] == 22.5
    assert body["water_temp_f"] == 72.5
    assert "water_temp_updated_at_iso" in body
    assert "water_temp_staleness_label" in body
    assert body["water_temp_is_stale"] is False


def test_api_payload_omits_water_temp_when_feature_disabled() -> None:
    """When the cache row's feature_enabled=False (operator flag was OFF at
    fetch time), /api/conditions must NOT emit any water_temp_* fields.
    This is the prod-safe default behavior."""
    from datetime import UTC, datetime

    from fastapi.testclient import TestClient

    from app.db.database import SessionLocal
    from app.main import app

    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        _seed_water_temp_cache(
            db,
            {
                "site": "09426630",
                "water_temp_c": None,
                "water_temp_f": None,
                "observed_at": None,
                "feature_enabled": False,
                "history": [],
            },
            now=now,
        )

    client = TestClient(app)
    r = client.get("/api/conditions")
    assert r.status_code == 200
    body = r.json()
    assert "water_temp_c" not in body
    assert "water_temp_f" not in body
    assert "water_temp_updated_at_iso" not in body
    assert "water_temp_staleness_label" not in body
    assert "water_temp_is_stale" not in body


def test_view_model_renders_water_temp_tile_when_reading_present() -> None:
    """When water_temp_f is present in the api payload, the view model
    surfaces a kind=water_temp tile with the gotcha #23 attribution chip."""
    from datetime import UTC, datetime

    from app.conditions.view_model import build_conditions_strip_view_model
    from app.db.database import SessionLocal

    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        _seed_water_temp_cache(
            db,
            {
                "site": "09426630",
                "water_temp_c": 23.3,
                "water_temp_f": 73.9,
                "observed_at": "2026-05-23T18:00:00+00:00",
                "feature_enabled": True,
                "history": [],
            },
            now=now,
        )

        vm = build_conditions_strip_view_model(db, now=now)

    water_tiles = [t for t in vm.tiles if t.kind == "water_temp"]
    assert len(water_tiles) == 1
    tile = water_tiles[0]
    # Primary value is rounded F to keep the strip tidy.
    assert tile.primary_value == "74°F"
    # Secondary value carries the Celsius reading for the science audience.
    assert "23.3" in (tile.secondary_value or "")
    # Per gotcha #23 (honest spatial attribution), the chip names the
    # station + distance / direction from Lake Havasu City.
    assert tile.attribution_chip == "USGS 09426630 ~25mi south"
    assert tile.severity == "neutral"
    assert tile.visible is True


def test_view_model_skips_water_temp_tile_when_reading_is_sentinel() -> None:
    """When the gage is sentinel-valued (api payload sees feature_enabled
    True but water_temp_f None), the view model degrades gracefully by
    omitting the tile rather than rendering a None value."""
    from datetime import UTC, datetime

    from app.conditions.view_model import build_conditions_strip_view_model
    from app.db.database import SessionLocal

    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        _seed_water_temp_cache(
            db,
            {
                "site": "09426630",
                "water_temp_c": None,
                "water_temp_f": None,
                "observed_at": None,
                "feature_enabled": True,
                "history": [
                    {
                        "parameter_code": "00010",
                        "value": None,
                        "observed_at": "2026-05-21T17:00:00+00:00",
                        "is_sentinel": True,
                    }
                ],
            },
            now=now,
        )

        vm = build_conditions_strip_view_model(db, now=now)

    water_tiles = [t for t in vm.tiles if t.kind == "water_temp"]
    assert water_tiles == []
