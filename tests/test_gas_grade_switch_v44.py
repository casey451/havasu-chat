"""v4.4 PR-6 — gas grade switch: per-grade top-5, drop-off, tile echo (Δ8).

The home panel and /gas page let you switch fuel grade. This pins the data the
switch runs on: each grade's cheapest-5 (stations without that grade drop off,
no dashes), the strip-tile echo string, and the single-grade suppression rule.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.conditions.cache import CacheReadResult
from app.home import redesign
from app.main import app


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _payload(stations: list[dict]) -> dict:
    return {"stations": stations, "cheapest": stations}


def _panel(stations: list[dict]) -> dict:
    result = CacheReadResult(data=_payload(stations), fetched_at=_now(), ttl_seconds=86400, is_stale=False)
    with patch("app.home.redesign.read_source", return_value=result):
        return redesign.gas_panel_data(None)  # type: ignore[arg-type]


_MIXED = [
    {"name": "A", "address": "1 St", "prices": {"regular": 3.5, "diesel": 4.8}},
    {"name": "B", "address": "2 St", "prices": {"regular": 3.2}},  # no diesel
    {"name": "C", "address": "3 St", "prices": {"regular": 3.9, "diesel": 4.5}},
]


def test_grades_available_reflects_data() -> None:
    panel = _panel(_MIXED)
    assert panel["grades"] == ["reg", "dsl"]  # midgrade/premium absent
    assert panel["single_grade"] is False


def test_per_grade_top5_and_dropoff() -> None:
    panel = _panel(_MIXED)
    # Regular: all three, cheapest first.
    assert [r["name"] for r in panel["by_grade"]["reg"]] == ["B", "A", "C"]
    assert panel["cheapest"] == panel["by_grade"]["reg"]  # server renders regular
    # Diesel: B drops off (no diesel), cheapest-diesel first.
    diesel = panel["by_grade"]["dsl"]
    assert [r["name"] for r in diesel] == ["C", "A"]
    assert all(r["price"].startswith("$") for r in diesel)


def test_tile_echo_strings() -> None:
    panel = _panel(_MIXED)
    # Regular carries no suffix (default, un-annotated); its value is the cheapest.
    assert panel["echo"]["reg"] == {"suffix": "", "value": "$3.20"}
    # Diesel echoes " · Diesel"-style suffix + its cheapest value.
    assert panel["echo"]["dsl"]["suffix"] == "Diesel"
    assert panel["echo"]["dsl"]["value"] == "$4.50"


def test_single_grade_suppresses_the_segment() -> None:
    only_reg = [{"name": "A", "address": "1 St", "prices": {"regular": 3.5}}]
    panel = _panel(only_reg)
    assert panel["grades"] == ["reg"]
    assert panel["single_grade"] is True


def test_panel_a11y_attributes_render() -> None:
    result = CacheReadResult(data=_payload(_MIXED), fetched_at=_now(), ttl_seconds=86400, is_stale=False)
    with patch("app.home.redesign.read_source", return_value=result):
        with TestClient(app) as client:
            html = client.get("/home").text
    # The list container is a polite live region; segment buttons carry aria-pressed.
    assert 'id="gasList"' in html and 'aria-live="polite"' in html
    assert 'id="gasSeg"' in html
    assert "aria-pressed" in html
