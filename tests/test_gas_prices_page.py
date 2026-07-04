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


def test_gas_page_extends_v4_shell_and_loads_v4_css() -> None:
    # v4.5 PR-2: /gas is in the v4 language (base_redesign + lake_redesign.css); the
    # old base_lake sheet and the page-specific lake_conditions.css are gone.
    body = _get_gas(_result(_payload(), fetched_at=_now() - timedelta(minutes=5)))
    assert "/static/styles/lake_redesign.css" in body  # the v4 shell stylesheet
    assert "/static/styles/lake_conditions.css" not in body  # old page sheet gone
    assert "/static/styles/lake.css" not in body  # old base_lake sheet gone


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
    # Relative + recent so the v4.4 >7d honest-hide rule (PR-1) keeps the board
    # live; the test only cares that the label/timestamp track fetched_at, not the
    # payload's bogus 2099 updated_at_iso.
    fetched = _now() - timedelta(hours=3)
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


# -- WP-8: humanized timestamp, 2-decimal avg, copy + single "Updated" -------


def test_cheapest_heading_is_today_as_of_time() -> None:
    """N-27 / M-10: the cheapest strip heading reads 'Cheapest today (as of
    {time})' on the live render path, not 'Cheapest right now'."""
    # 21:30 UTC -> 2:30 PM Lake Havasu (America/Phoenix, UTC-7). Anchored to
    # yesterday so it stays within the v4.4 >7d honest-hide window (PR-1).
    fetched = (_now() - timedelta(days=1)).replace(hour=21, minute=30, second=0, microsecond=0)
    body = _get_gas(_result(_payload(), fetched_at=fetched))
    assert "Cheapest today (as of" in body
    assert "Cheapest right now" not in body
    # The "as of" clause carries a time-only label derived from fetched_at.
    assert "as of 2:30 PM" in body


def test_single_updated_phrasing() -> None:
    """M-11: the page says 'Updated' exactly once (the freshness banner), so the
    header's absolute timestamp and the banner can't read as two updates."""
    fetched = _now() - timedelta(hours=3)  # recent -> board stays live post-PR-1
    body = _body_only(_get_gas(_result(_payload(), fetched_at=fetched)))
    assert body.count("Updated") == 1


def test_city_average_two_decimals() -> None:
    """M-10: averages render with exactly two decimals on the live render path."""
    payload = _payload()
    payload["city_avg"] = {"regular": 3.7, "midgrade": 3.999, "premium": 4.0}
    body = _get_gas(_result(payload, fetched_at=_now() - timedelta(minutes=5)))
    assert "$3.70" in body  # 3.7 -> two decimals
    assert "$4.00" in body  # 4.0 -> two decimals


def test_gas_page_carries_shell_nav() -> None:
    """The /gas page wears the full Lake shell: the header nav links render."""
    body = _get_gas(_result(_payload(), fetched_at=_now() - timedelta(minutes=5)))
    assert 'href="/events-ui"' in body  # a primary-nav link from the lake header


def test_gas_page_renders_v4_cond_strip_with_plain_gas_tile() -> None:
    """v4.5 PR-2: /gas wears the v4 cond-tile strip. Its gas tile is a PLAIN span
    here (no caret/panel — you're already on the gas page), so the expandable
    #gasPanel never renders.

    The strip's gas tile reads gas via the home builder's own ``read_source``
    import, so we patch that one too (alongside the gas-route patch)."""
    from app.home import router as home_router

    payload = _payload()
    result = _result(payload, fetched_at=_now() - timedelta(minutes=5))
    with patch.object(gas_route, "read_source", return_value=result):
        with patch.object(home_router, "read_source", return_value=result):
            with TestClient(app) as client:
                body = client.get("/gas").text
    assert 'class="cond"' in body  # v4 conditions strip
    assert 'id="gasPanel"' not in body  # no expandable panel on the gas page
    assert 'id="gasTile"' not in body  # gas tile is a plain span, not the toggle button


def test_format_fetched_at_helpers_are_lake_local() -> None:
    """G-1: both timestamp helpers humanize fetched_at in Lake Havasu local time
    (America/Phoenix, UTC-7, no DST) from a naive-UTC input."""
    # 21:30 UTC -> 14:30 (2:30 PM) Phoenix.
    fetched = datetime(2026, 6, 2, 21, 30, 0)
    assert gas_route._format_fetched_at(fetched) == "Jun 2, 2026 2:30 PM"
    assert gas_route._format_fetched_at_time(fetched) == "2:30 PM"
