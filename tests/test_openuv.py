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
