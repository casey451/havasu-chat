"""Sandstone gas-prices page — re-skin + the four §4.11 fixes.

Covers (UI build guide §4.11):
1. No "Source" column and no Google-feed footer line.
2. Freshness banner can't contradict its own timestamp (label + timestamp
   both derive from the SAME ``row.fetched_at`` clock).
3. The cheapest strip shows up to 6 stations (not a cut-off "top 5").
4. The pump disclaimer stays; the Google-feed line is gone.
Plus anti-confabulation: no data -> honest empty state, never a fake price.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.routes import gas as gas_route
from app.conditions.cache import CacheReadResult
from app.main import app


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _body_only(html: str) -> str:
    """The <body>..</body> slice, so <head> meta copy doesn't trip assertions."""
    start = html.find("<body")
    return html[start:] if start != -1 else html


def _station(name: str, regular: float, *, slug: str | None = None) -> dict:
    s = {
        "source": "gasbuddy",
        "name": name,
        "brand": "Shell",
        "address": f"{name} Rd, Lake Havasu City",
        "prices": {"regular": regular, "midgrade": regular + 0.30, "premium": regular + 0.60},
    }
    if slug:
        s["provider_slug"] = slug
    return s


def _payload(n_stations: int = 8) -> dict:
    stations = [_station(f"Station {i}", 3.50 + i * 0.05, slug=f"station-{i}") for i in range(n_stations)]
    return {
        "updated_at_iso": "2099-01-01T00:00:00",  # deliberately bogus / separate clock
        "station_count": len(stations),
        "source_counts": {"gasbuddy": len(stations), "google": 0},
        "city_avg": {"regular": 3.69, "midgrade": 3.99, "premium": 4.29},
        "cheapest": stations[:5],  # builder still stores 5; route widens the view
        "stations": stations,
    }


def _result(payload: dict, *, fetched_at: datetime, is_stale: bool = False) -> CacheReadResult:
    return CacheReadResult(data=payload, fetched_at=fetched_at, ttl_seconds=86400, is_stale=is_stale)


def _get_gas(result: CacheReadResult | None) -> str:
    with patch.object(gas_route, "read_source", return_value=result):
        with TestClient(app) as client:
            resp = client.get("/gas")
    assert resp.status_code == 200
    return resp.text


def test_gas_page_extends_sandstone_and_loads_gas_css() -> None:
    body = _get_gas(_result(_payload(), fetched_at=_now() - timedelta(minutes=5)))
    assert "/static/styles/sandstone.css" in body  # from sandstone_base
    assert "/static/styles/sandstone_gas.css" in body  # page-specific, separate file
    assert "/static/styles/lake_light.css" not in body  # old skin gone


def test_no_source_column_and_no_google_feed_line() -> None:
    body = _get_gas(_result(_payload(), fetched_at=_now() - timedelta(minutes=5)))
    # Fix 1: the per-row Source column header is gone.
    assert ">Source<" not in body
    # Fix 4: the Google official-feed footer wording is gone.
    assert "Google" not in body
    assert "crowd-sourced" not in body
    # ...but the pump disclaimer stays.
    assert "confirm at the pump" in body
    assert "update once daily" in body or "update daily" in body


def test_freshness_label_and_timestamp_share_one_clock() -> None:
    """Fix 2: the banner's staleness label and the displayed timestamp both
    derive from row.fetched_at, so they cannot disagree."""
    fetched = datetime(2026, 6, 2, 14, 30, 0)
    body = _get_gas(_result(_payload(), fetched_at=fetched))
    # The header timestamp is rendered from fetched_at, NOT the payload's bogus
    # updated_at_iso (2099) — proving a single source of truth.
    assert "2026" in body
    assert "2099" not in body
    # And the staleness label (computed from the same fetched_at) is present.
    assert "Updated" in body


def test_shows_six_cheapest_not_five() -> None:
    """Fix 3: up to 6 cheapest cards render (no cut-off top 5)."""
    fetched = _now() - timedelta(minutes=5)
    # Route slices data["stations"]... actually it slices data["cheapest"]; give 6+.
    payload = _payload(8)
    payload["cheapest"] = payload["stations"][:8]
    body = _get_gas(_result(payload, fetched_at=fetched))
    # Six ranked cards => #1..#6 present, #7 absent.
    for n in range(1, 7):
        assert f"#{n}" in body
    assert "#7" not in body


def test_city_average_rendered_prominently() -> None:
    body = _get_gas(_result(_payload(), fetched_at=_now() - timedelta(minutes=5)))
    assert "City average" in body
    assert "$3.69" in body  # regular city avg, formatted


def test_no_data_renders_honest_empty_state_never_a_price() -> None:
    """Anti-confabulation: missing data -> honest empty state, no fake price."""
    body = _get_gas(None)
    assert "No gas prices yet" in body
    # No price cards, no city-average figure, no table: never a guessed price.
    assert "gas-card" not in body
    assert "gas-avg-price" not in body
    assert "gas-table" not in body
    assert "$" not in _body_only(body)  # nothing in the page body looks like a price


def test_stale_banner_flags_out_of_date() -> None:
    fetched = _now() - timedelta(days=3)
    body = _get_gas(_result(_payload(), fetched_at=fetched, is_stale=True))
    assert "out of date" in body
