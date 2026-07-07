"""Unit tests for the cold-cache freshness + route-health canary.

The canary itself hits live production; these tests exercise its pure decision
core (``run_checks``) offline with fabricated responses, so every failure branch
is regression-covered without a network. A green fixture must pass clean; each
seeded defect (stale date, split gas prices, blank nav page, old gas feed, 404)
must produce exactly the expected complaint.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from scripts.freshness_canary import (
    DATED_PAGES,
    NAV_PAGES,
    NAV_REDIRECTS,
    Resp,
    extract_cheapest_gas,
    phoenix_today_label,
    run_checks,
)

# A fixed instant: 2099-07-06 19:00 UTC == 12:00 Phoenix (MST, no DST) → the
# rendered label is "Monday, July 6".
_NOW = datetime(2099, 7, 6, 19, 0, tzinfo=UTC)
_LABEL = "Monday, July 6"


def _page(*, label: str = _LABEL, price: str | None = "$3.59", body: str = "x" * 800) -> str:
    """A healthy dated page: today's label, a fat <main>, optional gas chip."""
    gas = f'<span class="gr num">{price}</span>' if price else ""
    return (
        f"<header><span class='r'>{label}</span>{gas}</header>"
        f'<main id="main">{body}</main>'
    )


def _gas_json(*, now: datetime = _NOW, hours_old: float = 0.5, is_stale: bool = False,
              cheapest: bool = True) -> str:
    pulled = now - timedelta(hours=hours_old)
    return json.dumps(
        {
            "cheapest": [{"name": "Love's", "price": "$3.59"}] if cheapest else [],
            "updated_at_iso": pulled.isoformat(),
            "is_stale": is_stale,
            "staleness_label": "Updated 30 min ago",
        }
    )


def _make_fetch(overrides: dict[str, Resp] | None = None):
    """A fetcher where every URL is healthy unless overridden."""
    overrides = overrides or {}

    def fetch(path: str) -> Resp:
        if path in overrides:
            return overrides[path]
        if path == "/api/gas":
            return Resp(200, _gas_json())
        if path in NAV_REDIRECTS:
            return Resp(301, "", location="/somewhere")
        return Resp(200, _page())

    return fetch


def test_phoenix_label_is_unpadded() -> None:
    assert phoenix_today_label(_NOW) == "Monday, July 6"


def test_extract_cheapest_gas_normalizes_dollar() -> None:
    assert extract_cheapest_gas('<span class="gr num">3.59</span>') == "$3.59"
    assert extract_cheapest_gas('<span class="gr num">$3.59</span>') == "$3.59"
    assert extract_cheapest_gas("<span>no gas here</span>") is None


def test_all_green_fixture_passes_clean() -> None:
    assert run_checks(_make_fetch(), _NOW) == []


def test_stale_date_on_a_dated_page_fails() -> None:
    stale = Resp(200, _page(label="Sunday, June 28"))
    failures = run_checks(_make_fetch({"/events-ui": stale}), _NOW)
    assert any("/events-ui" in f and _LABEL in f for f in failures)
    assert len(failures) == 1


def test_split_gas_prices_across_pages_fail() -> None:
    # /home shows $4.19 while everything else shows $3.59 — the edge-divergence bug.
    failures = run_checks(_make_fetch({"/home": Resp(200, _page(price="$4.19"))}), _NOW)
    assert any("multiple cheapest-gas prices" in f for f in failures)


def test_blank_nav_page_fails_route_health() -> None:
    # A nav link that returns 200 with an empty <main> is the B2 blank-page defect.
    blank = Resp(200, '<main id="main"></main>')
    failures = run_checks(_make_fetch({"/seniors": blank}), _NOW)
    assert any("/seniors" in f and "empty" in f for f in failures)


def test_404_on_nav_page_fails() -> None:
    failures = run_checks(_make_fetch({"/news": Resp(404, "")}), _NOW)
    assert any("/news" in f and "404" in f for f in failures)


def test_redirect_nav_url_404_fails_but_3xx_passes() -> None:
    # /lake normally 301s (healthy). A 404 there is a broken nav link.
    ok = run_checks(_make_fetch(), _NOW)
    assert not any("/lake" in f for f in ok)
    bad = run_checks(_make_fetch({"/lake": Resp(404, "")}), _NOW)
    assert any("/lake" in f for f in bad)


def test_old_gas_feed_fails() -> None:
    old = Resp(200, _gas_json(hours_old=30))
    failures = run_checks(_make_fetch({"/api/gas": old}), _NOW)
    assert any("/api/gas" in f and "old" in f for f in failures)


def test_stale_flagged_gas_fails() -> None:
    stale = Resp(200, _gas_json(is_stale=True))
    failures = run_checks(_make_fetch({"/api/gas": stale}), _NOW)
    assert any("/api/gas" in f and "is_stale" in f for f in failures)


def test_gas_endpoint_500_fails() -> None:
    failures = run_checks(_make_fetch({"/api/gas": Resp(500, "")}), _NOW)
    assert any("/api/gas" in f and "500" in f for f in failures)


def test_dated_page_500_fails() -> None:
    failures = run_checks(_make_fetch({"/gas": Resp(500, "")}), _NOW)
    assert any("/gas" in f and "500" in f for f in failures)


def test_url_sets_are_disjoint_and_nonempty() -> None:
    # Sanity: no URL double-classified, and the sets aren't accidentally empty.
    assert DATED_PAGES and NAV_PAGES and NAV_REDIRECTS
    assert not (set(DATED_PAGES) & set(NAV_PAGES))
    assert not (set(NAV_PAGES) & set(NAV_REDIRECTS))
    assert not (set(DATED_PAGES) & set(NAV_REDIRECTS))
