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
    SAMPLE_UAS,
    Resp,
    calendar_month_variants,
    extract_cheapest_gas,
    phoenix_today_label,
    run_checks,
    run_checks_with_retry,
)

# A fixed instant: 2099-07-06 19:00 UTC == 12:00 Phoenix (MST, no DST) → the
# rendered label is "Monday, July 6".
_NOW = datetime(2099, 7, 6, 19, 0, tzinfo=UTC)
_LABEL = "Monday, July 6"
_SHA = "abc123def456"


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _page(
    *,
    label: str = _LABEL,
    price: str | None = "$3.59",
    body: str = "x" * 800,
    sha: str | None = _SHA,
    rendered: datetime | None = None,
) -> str:
    """A healthy dated page: today's label, a fat <main>, optional gas chip, and
    the freshness metas (build-sha + render-ts) — fresh by default."""
    gas = f'<span class="gr num">{price}</span>' if price else ""
    meta = ""
    if sha is not None:
        meta += f'<meta name="build-sha" content="{sha}">'
    meta += f'<meta name="render-ts" content="{_ts(rendered or _NOW)}">'
    return (
        f"<head>{meta}</head>"
        f"<header><span class='r'>{label}</span>{gas}</header>"
        f'<main id="main">{body}</main>'
    )


def _health_json(*, sha: str = _SHA) -> str:
    return json.dumps({"status": "ok", "db_connected": True, "build_sha": sha})


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


def _make_fetch(overrides: dict | None = None, *, ua_overrides: dict | None = None):
    """A fetcher where every URL is healthy unless overridden.

    ``overrides`` is keyed by path (any UA). ``ua_overrides`` is keyed by
    ``(path, ua_name)`` to simulate a UA-keyed edge cache freezing one variant.
    """
    overrides = overrides or {}
    ua_overrides = ua_overrides or {}
    _ua_name = {ua: name for name, ua in SAMPLE_UAS}

    def fetch(path: str, ua: str | None = None) -> Resp:
        key = (path, _ua_name.get(ua or ""))
        if key in ua_overrides:
            return ua_overrides[key]
        if path in overrides:
            return overrides[path]
        if path == "/health":
            return Resp(200, _health_json())
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
    # /ask 302s to /chat (healthy). A 404 there is a broken nav link. (/lake is a
    # content NAV_PAGE now — WS10 — so /ask is the redirect example here.)
    ok = run_checks(_make_fetch(), _NOW)
    assert not any("/ask" in f for f in ok)
    bad = run_checks(_make_fetch({"/ask": Resp(404, "")}), _NOW)
    assert any("/ask" in f for f in bad)


def test_stale_sampled_subcategory_leaf_fails() -> None:
    # The 2026-07-09 class: a bare /categories/{dept}/{leaf} frozen at an edge PoP
    # (older build-sha). The canary samples leaves from the sitemap and sweeps them
    # across UAs, so a stale one turns red. Here the sitemap advertises one leaf and
    # that leaf serves a wrong build-sha for every UA.
    leaf = "/categories/eat-and-drink/quick-bites"
    sitemap = Resp(200, f"<url><loc>https://askhava.com{leaf}</loc></url>")
    stale_leaf = Resp(200, _page(sha="oldbuild0000"))
    failures = run_checks(
        _make_fetch({"/sitemap-pages.xml": sitemap, leaf: stale_leaf}), _NOW
    )
    assert any(leaf in f and "STALE" in f for f in failures)


def test_fresh_sampled_subcategory_leaf_passes() -> None:
    # Same sampling path, but the leaf is fresh (current build-sha) → no complaint.
    leaf = "/categories/auto/boat-repair"
    sitemap = Resp(200, f"<url><loc>https://askhava.com{leaf}</loc></url>")
    failures = run_checks(_make_fetch({"/sitemap-pages.xml": sitemap}), _NOW)
    assert not any(leaf in f for f in failures)


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


def test_stale_build_sha_fails() -> None:
    # A page served from an OLDER build than the running app (edge/CDN copy). Its
    # date label is fine — only the build-sha mismatch catches it (Casey's case).
    old_build = Resp(200, _page(sha="oldsha000000"))
    failures = run_checks(_make_fetch({"/events-ui": old_build}), _NOW)
    assert any("/events-ui" in f and "STALE render" in f for f in failures)


def test_old_render_ts_fails() -> None:
    # Same build + today's date, but rendered 3h ago (a same-day cached copy).
    stale = Resp(200, _page(rendered=_NOW - timedelta(hours=3)))
    failures = run_checks(_make_fetch({"/events-ui": stale}), _NOW)
    assert any("/events-ui" in f and "rendered" in f and "ago" in f for f in failures)


def test_missing_freshness_meta_fails() -> None:
    no_meta = Resp(200, f'<header><span class="r">{_LABEL}</span></header>'
                        f'<main id="main">{"x" * 800}</main>')
    failures = run_checks(_make_fetch({"/events-ui": no_meta}), _NOW)
    assert any("/events-ui" in f and "build-sha" in f for f in failures)
    assert any("/events-ui" in f and "render-ts" in f for f in failures)


def test_one_stale_ua_variant_fails_even_if_others_fresh() -> None:
    # The 2026-07-07 case: googlebot fresh, but a generic-fetcher UA gets a frozen
    # pre-deploy copy. One green UA is NOT green — the stale variant must fail.
    stale = Resp(200, _page(sha="oldsha000000"))
    failures = run_checks(_make_fetch(ua_overrides={("/events-ui", "curl"): stale}), _NOW)
    assert any("/events-ui [curl]" in f and "STALE render" in f for f in failures)
    # ...and the other UAs on that page do NOT fail.
    assert not any("/events-ui [chrome]" in f for f in failures)


def test_all_three_uas_are_sampled() -> None:
    seen: set[str] = set()

    def fetch(path: str, ua: str | None = None) -> Resp:
        if path == "/events-ui":
            seen.add(ua or "")
        if path == "/health":
            return Resp(200, _health_json())
        if path == "/api/gas":
            return Resp(200, _gas_json())
        if path in NAV_REDIRECTS:
            return Resp(301, "")
        return Resp(200, _page())

    run_checks(fetch, _NOW)
    assert {ua for _, ua in SAMPLE_UAS} <= seen  # every sample UA hit the page


def test_specific_date_day_view_is_freshness_checked() -> None:
    # The exact surface Casey hit: /events-ui?date=<today>. No "today" label to
    # lean on — a stale build there is caught only by build-sha.
    day = "/events-ui?date=" + _NOW.date().isoformat()
    failures = run_checks(_make_fetch({day: Resp(200, _page(sha="oldsha000000"))}), _NOW)
    assert any(day in f and "STALE render" in f for f in failures)


def test_calendar_month_variants_are_current_and_next() -> None:
    # 2099-07-06 Phoenix → current 2099-07, next 2099-08. December rolls the year.
    assert calendar_month_variants(_NOW) == ("2099-07", "2099-08")
    dec = datetime(2099, 12, 20, 19, 0, tzinfo=UTC)
    assert calendar_month_variants(dec) == ("2099-12", "2100-01")


def test_calendar_cal_month_variant_is_freshness_checked() -> None:
    # The 2026-07-08 re-audit case: /calendar?cal=<month> frozen at an edge PoP
    # (older build) while bare /calendar was fresh. The ?cal= key is checked now.
    cal = "/calendar?cal=" + calendar_month_variants(_NOW)[0]
    failures = run_checks(_make_fetch({cal: Resp(200, _page(sha="oldsha000000"))}), _NOW)
    assert any(cal in f and "STALE render" in f for f in failures)


def test_health_unreadable_disables_sha_match_but_flags() -> None:
    failures = run_checks(_make_fetch({"/health": Resp(500, "")}), _NOW)
    assert any("/health" in f and "build_sha" in f for f in failures)


def test_url_sets_are_disjoint_and_nonempty() -> None:
    # Sanity: no URL double-classified, and the sets aren't accidentally empty.
    assert DATED_PAGES and NAV_PAGES and NAV_REDIRECTS
    assert not (set(DATED_PAGES) & set(NAV_PAGES))
    assert not (set(NAV_PAGES) & set(NAV_REDIRECTS))
    assert not (set(DATED_PAGES) & set(NAV_REDIRECTS))


# ── retry-once-before-fail (deploy-window transient suppression) ──────────────
def test_retry_clears_a_deploy_window_transient() -> None:
    # Pass 1: /events-ui served from an OLD build (a PoP the deploy hasn't reached
    # yet). The "settle" flips the deploy to done, so pass 2 is fresh → no alert.
    state = {"deployed": False}

    def fetch(path: str, ua: str | None = None) -> Resp:
        if not state["deployed"] and path == "/events-ui":
            return Resp(200, _page(sha="oldsha000000"))
        return _make_fetch()(path, ua)

    def settle(_seconds: float) -> None:
        state["deployed"] = True

    failures = run_checks_with_retry(fetch, _NOW, sleep=settle, clock=lambda: _NOW)
    assert failures == []  # the deploy-window transient cleared on the retry


def test_retry_still_reports_a_persistent_failure() -> None:
    # /events-ui is stale on BOTH passes — a real, persistent staleness must page.
    def fetch(path: str, ua: str | None = None) -> Resp:
        if path == "/events-ui":
            return Resp(200, _page(sha="oldsha000000"))
        return _make_fetch()(path, ua)

    failures = run_checks_with_retry(fetch, _NOW, sleep=lambda _s: None, clock=lambda: _NOW)
    assert any("/events-ui" in f and "STALE render" in f for f in failures)


def test_retry_skipped_when_first_pass_is_clean() -> None:
    slept: list[float] = []
    failures = run_checks_with_retry(
        _make_fetch(), _NOW, sleep=lambda s: slept.append(s), clock=lambda: _NOW
    )
    assert failures == [] and slept == []  # a clean first pass never retries/sleeps
