"""P0 Task 5 — slim utility strip + removal of the redundant home blocks."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.conditions.view_model import ConditionsStripViewModel, ConditionsTile
from app.db.database import SessionLocal
from app.home import router as home_router
from app.main import app


def _tile(kind: str, value: str) -> ConditionsTile:
    return ConditionsTile(
        kind=kind,
        primary_value=value,
        secondary_value=None,
        attribution_chip="NWS",
        severity="neutral",
        staleness_label="Updated recently",
        is_stale=False,
        detail_text=None,
        visible=True,
    )


def test_utility_chips_combines_gas_and_conditions() -> None:
    gas = {
        "has_data": True,
        "staleness_label": "Updated 10m ago",
        "is_stale": False,
        "cheapest": [{"station_name": "Loves", "prices": {"regular": 4.29}}],
    }
    # Phase 1 strip = temp · UV · wind · gas. AQI + water-temp tiles are present in
    # the view model but deliberately excluded from the strip.
    vm = ConditionsStripViewModel(
        tiles=(
            _tile("temp", "99°F"),
            _tile("aqi", "AQI 55"),
            _tile("wind", "7 mph"),
            _tile("uv", "UV 8"),
            _tile("water_temp", "72°F"),
        ),
        any_source_stale=False,
        rendered_at=datetime.now(),  # type: ignore[attr-defined]
        has_data=True,
    )
    with (
        patch.object(home_router, "_gas_snapshot", return_value=gas),
        patch.object(home_router, "build_conditions_strip_view_model", return_value=vm),
    ):
        chips = home_router._utility_chips(SessionLocal())

    kinds = [c["kind"] for c in chips]
    # Fixed order temp · UV · wind · gas; gas closes the strip.
    assert kinds == ["weather", "uv", "wind", "gas"]
    # AQI + water temp are dropped from the strip (still on /today + the JSON).
    assert "air" not in kinds
    assert "water" not in kinds
    gas_chip = chips[-1]
    assert gas_chip["value"] == "$4.29"
    assert gas_chip["href"] == "/gas"
    assert "Loves" in gas_chip["detail"]


def test_home_renders_slim_strip_and_drops_redundant_blocks() -> None:
    sample = {
        "kind": "gas",
        "icon": "⛽",
        "value": "$4.29",
        "label": "Cheapest gas",
        "detail": "Loves · regular, per gallon",
        "source": None,
        "freshness": "Updated 10m ago",
        "is_stale": False,
        "severity": "neutral",
        "href": "/gas",
    }
    with patch.object(home_router, "_gas_chip", return_value=sample):
        with TestClient(app) as client:
            body = client.get("/home").text
    # Lake gas line present, with its tap-through to the full gas list...
    assert 'class="gaschip' in body
    assert "$4.29" in body
    assert 'href="/gas"' in body
    # ...and no fabricated/redundant full-width blocks.
    assert "Fuel before you head out" not in body
    assert "All seven buckets" not in body


def test_home_ribbon_absent_without_data() -> None:
    """No gas data -> no empty gas line shell (graceful omission)."""
    with patch.object(home_router, "_gas_chip", return_value=None):
        with TestClient(app) as client:
            body = client.get("/home").text
    assert 'class="gaschip' not in body
    assert "All seven buckets" not in body


def test_utility_chips_gracefully_empty_when_no_data() -> None:
    with (
        patch.object(home_router, "_gas_snapshot", return_value={"has_data": False}),
        patch.object(
            home_router,
            "build_conditions_strip_view_model",
            return_value=ConditionsStripViewModel(
                tiles=(), any_source_stale=False, rendered_at=datetime.now(), has_data=False
            ),
        ),
    ):
        assert home_router._utility_chips(SessionLocal()) == []
