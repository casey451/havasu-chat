"""UV index via Open-UV — key-gated optional conditions source (P0 follow-up).

No live API calls: the fetcher self-gates on OPENUV_API_KEY and all HTTP is
mocked. With no key the source is a graceful no-op; with a key it surfaces a UV
chip in the home utility strip.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from app.conditions import openuv
from app.conditions.constants import SOURCE_OPENUV


def _seed_uv_cache(db, payload: dict, *, now) -> None:
    from app.conditions.cache import invalidate_local_cache, upsert_source

    upsert_source(db, SOURCE_OPENUV, payload, now=now)
    invalidate_local_cache(SOURCE_OPENUV)


# --- fetcher (key gating + parsing) -----------------------------------------


def test_fetch_no_key_returns_empty_and_makes_no_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENUV_API_KEY", raising=False)
    with patch.object(openuv.httpx, "Client") as client:
        assert openuv.fetch_openuv_index() == {}
        client.assert_not_called()  # no HTTP without a key


def test_get_degrades_to_empty_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A keyed request that errors (rate limit / bad key / transport) returns {}.

    Regression: previously ``_get`` let ``raise_for_status`` propagate, which blew
    past the keyless EPA fallback in ``uv.fetch_uv_index`` and blanked the UV tile.
    """
    monkeypatch.setenv("OPENUV_API_KEY", "test-key")
    with patch.object(openuv.httpx, "Client") as client_cls:
        client_cls.return_value.__enter__.return_value.get.side_effect = openuv.httpx.ConnectError(
            "boom"
        )
        assert openuv._get() == {}


def test_fetch_parses_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENUV_API_KEY", "test-key")
    with patch.object(openuv, "_get", return_value={"result": {"uv": 7.3, "uv_max": 9.12}}):
        out = openuv.fetch_openuv_index()
    assert out["uv_index"] == 7.3
    assert out["uv_max"] == 9.1
    assert out["uv_severity"] == "warning"


def test_fetch_unusable_response_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENUV_API_KEY", "test-key")
    with patch.object(openuv, "_get", return_value={"nope": 1}):
        assert openuv.fetch_openuv_index() == {}


@pytest.mark.parametrize(
    "uv,sev",
    [(1.0, "good"), (4.0, "moderate"), (7.0, "warning"), (9.0, "severe")],
)
def test_severity_bands(uv: float, sev: str) -> None:
    assert openuv._uv_severity(uv) == sev


def test_fetch_extracts_true_sunset_from_sun_info(monkeypatch: pytest.MonkeyPatch) -> None:
    """WP-13: Open-UV's sun_info.sun_times carries the real astronomical sunset."""
    monkeypatch.setenv("OPENUV_API_KEY", "test-key")
    raw = {
        "result": {
            "uv": 5.0,
            "uv_max": 9.0,
            "sun_info": {
                "sun_times": {
                    "sunrise": "2026-06-04T12:30:00Z",
                    "sunset": "2026-06-05T02:42:00Z",
                }
            },
        }
    }
    with patch.object(openuv, "_get", return_value=raw):
        out = openuv.fetch_openuv_index()
    assert out["sunset_iso"] == "2026-06-05T02:42:00Z"
    assert out["sunrise_iso"] == "2026-06-04T12:30:00Z"
    # UV fields still surface alongside the sun times.
    assert out["uv_index"] == 5.0


def test_fetch_omits_sun_times_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENUV_API_KEY", "test-key")
    with patch.object(openuv, "_get", return_value={"result": {"uv": 5.0}}):
        out = openuv.fetch_openuv_index()
    assert "sunset_iso" not in out
    assert "sunrise_iso" not in out


# --- pipeline (payload + view model + chip) ---------------------------------


def test_api_payload_emits_uv_when_present() -> None:
    from app.conditions.api_payload import build_conditions_api_payload
    from app.db.database import SessionLocal

    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        _seed_uv_cache(db, {"uv_index": 6.4, "uv_max": 8.0, "uv_severity": "warning"}, now=now)
        payload = build_conditions_api_payload(db, now=now)
    assert payload["uv_index"] == 6.4
    assert payload["uv_severity"] == "warning"


def test_view_model_emits_uv_tile() -> None:
    from app.conditions.view_model import build_conditions_strip_view_model
    from app.db.database import SessionLocal

    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        _seed_uv_cache(db, {"uv_index": 6.4, "uv_max": 8.0, "uv_severity": "warning"}, now=now)
        vm = build_conditions_strip_view_model(db, now=now)
    uv_tiles = [t for t in vm.tiles if t.kind == "uv"]
    assert len(uv_tiles) == 1
    assert uv_tiles[0].primary_value == "UV 6.4"
    assert uv_tiles[0].severity == "warning"


def test_router_utility_tile_map_has_uv() -> None:
    from app.home import router

    chip_kind, icon, label = router._UTILITY_TILE_MAP["uv"]
    assert (chip_kind, label) == ("uv", "UV index")
    assert icon


def test_openuv_in_source_keys() -> None:
    from app.conditions.constants import SOURCE_KEYS, TTL_BY_SOURCE

    assert SOURCE_OPENUV in SOURCE_KEYS
    assert SOURCE_OPENUV in TTL_BY_SOURCE


# --- WP-13: sunset accuracy (OpenUV preferred over NWS approximation) --------


def test_api_payload_prefers_openuv_sunset_over_nws() -> None:
    """When Open-UV's true sunset is cached, api_payload emits it (not NWS 6 PM)."""
    from app.conditions.api_payload import build_conditions_api_payload
    from app.conditions.cache import invalidate_local_cache, upsert_source
    from app.conditions.constants import SOURCE_NWS_SUNSET
    from app.db.database import SessionLocal

    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        # NWS tonight-period startTime: the inaccurate ~6 PM approximation.
        upsert_source(
            db,
            SOURCE_NWS_SUNSET,
            {"sunset_iso": "2026-06-05T01:00:00Z", "periods": []},
            now=now,
        )
        # Open-UV true astronomical sunset: 02:42 UTC -> 7:42 PM Phoenix.
        upsert_source(
            db,
            SOURCE_OPENUV,
            {"uv_index": 5.0, "uv_severity": "moderate", "sunset_iso": "2026-06-05T02:42:00Z"},
            now=now,
        )
        db.commit()
    invalidate_local_cache()
    with SessionLocal() as db:
        api = build_conditions_api_payload(db, now=now)
    assert api.get("sunset_iso") == "2026-06-05T02:42:00Z"
    assert api.get("sunset_local") == "7:42 PM"
    assert api.get("sunset_source") == "openuv"


def test_api_payload_falls_back_to_nws_when_openuv_has_no_sunset() -> None:
    from app.conditions.api_payload import build_conditions_api_payload
    from app.conditions.cache import invalidate_local_cache, upsert_source
    from app.conditions.constants import SOURCE_NWS_SUNSET
    from app.db.database import SessionLocal

    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        upsert_source(
            db,
            SOURCE_NWS_SUNSET,
            {"sunset_iso": "2026-06-05T02:42:00Z", "periods": []},
            now=now,
        )
        # Open-UV present but with no sun_times (only UV) -> must fall back.
        upsert_source(
            db,
            SOURCE_OPENUV,
            {"uv_index": 5.0, "uv_severity": "moderate"},
            now=now,
        )
        db.commit()
    invalidate_local_cache()
    with SessionLocal() as db:
        api = build_conditions_api_payload(db, now=now)
    assert api.get("sunset_iso") == "2026-06-05T02:42:00Z"
    assert api.get("sunset_local") == "7:42 PM"
    assert api.get("sunset_source") == "nws_approx"
