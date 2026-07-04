"""Phase 5c — Lake Ink & Brass conditions surfaces: /today + /gas.

Both render on an empty DB (honest empty / "Unavailable" states), so the
flag-swap + a11y go through the real routes (TestClient). The populated layouts
(city average, cheapest grid, station table; available condition tiles) are
rendered directly with sample context.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from starlette.requests import Request
from test_ada_compliance import _A11yChecker

from app.api.routes.gas import templates as _gas_templates
from app.api.routes.today import templates as _today_templates
from app.main import app


def _req(path: str) -> Request:
    return Request({
        "type": "http", "method": "GET", "path": path, "raw_path": path.encode(),
        "query_string": b"", "headers": [(b"host", b"testserver")], "scheme": "http",
        "server": ("testserver", 80), "client": ("test", 1), "app": app,
    })


def _a11y(html: str) -> list[str]:
    checker = _A11yChecker()
    checker.feed(html)
    return checker.finish()


# ── /gas ────────────────────────────────────────────────────────────────────

def test_lake_gas_route_is_themed() -> None:
    # Route-level flag check only — data-independent. The gas conditions cache is
    # shared and the conftest sweep doesn't clear it, so under xdist a concurrent
    # test can seed gas rows; don't assert the empty state through the route.
    b = TestClient(app).get("/gas?theme=lake").text
    assert 'data-theme="lake"' in b
    assert "/static/styles/lake_redesign.css" in b  # v4.5 PR-2: the v4 shell stylesheet
    assert b.count("<h1") == 1
    assert not _a11y(b)


def test_lake_gas_empty_state() -> None:
    # Deterministic: render the has_data=False path directly so it never races a
    # test that seeds the shared conditions cache.
    b = _gas_templates.env.get_template("gas_prices_lake.html").render(
        request=_req("/gas"), data={}, has_data=False, is_stale=False,
        fetched_at_label=None, fetched_at_time_label=None, staleness_label=None,
        city_avg={}, grades=["regular", "midgrade", "premium", "diesel"],
        grade_labels={"regular": "Regular", "midgrade": "Mid", "premium": "Premium", "diesel": "Diesel"},
        cheapest=[], stations=[])
    assert 'data-theme="lake"' in b
    assert "No gas prices yet" in b  # honest empty state, never a guessed price
    assert b.count("<h1") == 1
    assert not _a11y(b)


_GAS = {
    "data": {"station_count": 3},
    "has_data": True, "is_stale": False,
    "fetched_at_label": "Jun 18, 2026 2:30 PM", "fetched_at_time_label": "2:30 PM",
    "staleness_label": "2 min ago",
    "city_avg": {"regular": 3.51, "midgrade": 3.71, "premium": 3.91, "diesel": 3.61},
    "grades": ["regular", "midgrade", "premium", "diesel"],
    "grade_labels": {"regular": "Regular", "midgrade": "Mid", "premium": "Premium", "diesel": "Diesel"},
    "cheapest": [
        {"provider_slug": "shell-main", "brand": "Shell", "prices": {"regular": 3.45}, "name": "Shell Main", "address": "123 Main St"},
        {"provider_slug": None, "brand": None, "prices": {"regular": 3.49}, "name": "Costco", "address": None},
    ],
    "stations": [
        {"provider_slug": "shell-main", "name": "Shell Main", "address": "123 Main St",
         "prices": {"regular": 3.45, "midgrade": 3.65, "premium": 3.85, "diesel": 3.55}},
    ],
}


def test_lake_gas_populated() -> None:
    b = _gas_templates.env.get_template("gas_prices_lake.html").render(request=_req("/gas"), **_GAS)
    assert 'data-theme="lake"' in b
    assert "$3.51" in b  # city average regular
    assert "Cheapest today" in b
    assert '/provider/shell-main' in b  # provider-backed station links out
    assert "Costco" in b  # non-linked station still renders
    assert "Updated Jun 18, 2026 2:30 PM" in b  # single freshness phrasing
    assert b.count("<h1") == 1
    assert not _a11y(b)


# ── /today ──────────────────────────────────────────────────────────────────

def test_lake_today_route() -> None:
    b = TestClient(app).get("/today?theme=lake").text
    assert 'data-theme="lake"' in b
    assert "/static/styles/lake_conditions.css" in b
    assert "Today in Havasu" in b
    assert b.count("<h1") == 1
    assert not _a11y(b)


def test_lake_today_populated_and_unavailable() -> None:
    fields = [
        {"label": "Lake level", "available": True, "primary": "448.2 ft",
         "secondary": "+0.3 ft today", "attribution": "USGS", "staleness_label": "2 hours ago", "is_stale": False},
        {"label": "Water temp", "available": False, "primary": "Unavailable",
         "is_stale": True, "staleness_label": "stale"},
    ]
    b = _today_templates.env.get_template("today_lake.html").render(
        request=_req("/today"), fields=fields, any_available=True, local_time_label="2:30 PM")
    assert "448.2 ft" in b and "USGS" in b  # available tile
    assert "Unavailable" in b  # honest unavailable tile
    assert b.count("<h1") == 1
    assert not _a11y(b)
