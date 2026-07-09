"""Cold-cache freshness + route-health canary (WS1.6 / WS2.4).

The 2026-07-06 acceptance audit (B1) reported that cold visitors and crawlers
were served days-old renders (a June "today", five concurrent gas prices) while
warm browser sessions were fresh — an edge-cache divergence the origin's
``no-cache`` header should prevent. This canary is the tripwire that catches a
recurrence: it fetches the PUBLIC site COLD (no cookies) with a bot-like UA and
asserts, from *outside* the CDN:

  * every "today"-dated page renders the current America/Phoenix date
    (a stale edge copy would show a past weekday);
  * the util-bar cheapest-gas price is identical across every page that shows it
    (the "five prices at once" symptom is edge copies cached at different times);
  * ``/api/gas`` is fresh (< ``GAS_MAX_AGE_HOURS`` old, not flagged stale) and
    actually has a cheapest price;
  * every nav-reachable URL returns a healthy response — 200 with a non-empty
    ``<main>`` or an allowed redirect — never a blank 200, a 404, or a 5xx
    (WS2 route health; a nav link that blanks is the B2 defect).

It exits non-zero on any failure so a scheduler (GitHub Actions / cron) alerts.

Design: :func:`run_checks` is pure — it takes an injected ``fetch`` callable and
the current UTC time, so ``tests/test_freshness_canary.py`` exercises every
branch offline with fabricated responses (no network in CI). :func:`main` wires
the real urllib fetcher (cold, bot UA, redirects NOT auto-followed so route
health can see the 3xx) and the wall clock.

Usage:
    python scripts/freshness_canary.py [--base https://askhava.com]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

LAKE_HAVASU_TZ = ZoneInfo("America/Phoenix")
DEFAULT_BASE = "https://askhava.com"

# A crawler UA with no cookie jar — the exact profile that reproduced B1 cold.
BOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
CURL_UA = "curl/8.4.0"
CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
# Sample every freshness-critical page with ≥3 UA classes: a UA-keyed edge cache
# can freeze ONE variant while another stays fresh (2026-07-07: a generic-fetcher
# UA got a pre-deploy render while Googlebot was fresh). One green UA is not green.
SAMPLE_UAS: tuple[tuple[str, str], ...] = (
    ("googlebot", BOT_UA),
    ("curl", CURL_UA),
    ("chrome", CHROME_UA),
)

# Gas older than this (or self-reported stale) fails the canary (spec WS1: gas
# ``updated_at`` must be < 24h). The app flags is_stale sooner (10h) — either
# trips the check.
GAS_MAX_AGE_HOURS = 24

# A healthy content page has real markup inside <main>; a blank/errored render
# collapses to almost nothing. Well below any real page, well above an empty one.
_MAIN_MIN_CHARS = 400

# A page's render must be recent. A same-day stale render (an old-build copy from
# earlier today) keeps today's date label and so slips the date check — but its
# <meta name="render-ts"> is hours old. This is the tripwire for that.
RENDER_MAX_AGE_HOURS = 2

# Pages whose content is anchored to "today". Each must render the current
# Phoenix date label and a non-empty <main>; util-bar gas prices are collected
# here for the single-price cross-check.
DATED_PAGES: tuple[str, ...] = (
    "/home",
    "/events-ui",
    "/events-ui?view=week",
    "/calendar",
    "/movies",
    "/map",
    "/gas",
)

# Every nav-reachable URL (site_header `_nav_full` + site_footer), classified.
# PAGES must be 200 + non-empty <main>. REDIRECTS may 3xx (they may also 200
# with content — either is healthy); a 404/5xx on any of them fails.
NAV_PAGES: tuple[str, ...] = (
    "/news",
    "/lake",      # WS10: a real content hub now (was a 301 to the category)
    "/family",
    "/seniors",
    "/categories",
    "/categories/eat-and-drink",
    "/portal",
    "/sponsor",
    "/chat",
    "/about",
    "/contact",
    "/help",
    "/privacy",
    "/terms",
)
NAV_REDIRECTS: tuple[str, ...] = (
    "/ask",       # 302 → /chat
    "/advertise",  # 301 → /sponsor
    "/account",   # 200 or 3xx to /login depending on auth state
)

_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})

# <span class="gr num">$3.59</span> — the util-bar cheapest-gas price.
_GAS_PRICE_RE = re.compile(r'class="gr num">\s*(\$?\d+\.\d{2})')
# Slice the <main> content region to gauge whether a page actually rendered.
_MAIN_RE = re.compile(r'<main[^>]*id="main"[^>]*>(.*?)</main>', re.DOTALL | re.IGNORECASE)
# Freshness stamps: <meta name="build-sha" content="..."> / <meta name="render-ts" ...>.
_BUILD_SHA_RE = re.compile(r'<meta\s+name="build-sha"\s+content="([^"]*)"', re.IGNORECASE)
_RENDER_TS_RE = re.compile(r'<meta\s+name="render-ts"\s+content="([^"]*)"', re.IGNORECASE)


@dataclass
class Resp:
    """A minimal HTTP response: status, body text, and Location (for redirects)."""

    status: int
    text: str = ""
    location: str | None = None


def phoenix_today_label(now_utc: datetime) -> str:
    """The exact date label the templates render, e.g. ``Monday, July 6``.

    Mirrors ``now.strftime("%A, %B ") + str(now.day)`` in the routes — no
    zero-padded day, so it matches the rendered string verbatim.
    """
    local = now_utc.astimezone(LAKE_HAVASU_TZ)
    return local.strftime("%A, %B ") + str(local.day)


def calendar_month_variants(now_utc: datetime) -> tuple[str, ...]:
    """Current + next Phoenix month as ``YYYY-MM`` for the ``?cal=`` canary.

    Computed from the clock (never hard-coded) so the probed months roll forward
    on their own — a hard-coded month would silently stop covering the live one.
    """
    local = now_utc.astimezone(LAKE_HAVASU_TZ)
    nxt_year, nxt_month = (local.year + 1, 1) if local.month == 12 else (local.year, local.month + 1)
    return (f"{local.year:04d}-{local.month:02d}", f"{nxt_year:04d}-{nxt_month:02d}")


def _main_len(html: str) -> int:
    m = _MAIN_RE.search(html)
    return len(m.group(1).strip()) if m else 0


def extract_cheapest_gas(html: str) -> str | None:
    """The first util-bar cheapest-gas price on the page, normalized ('$3.59'),
    or None if the page doesn't render the gas chip."""
    m = _GAS_PRICE_RE.search(html)
    if not m:
        return None
    price = m.group(1)
    return price if price.startswith("$") else f"${price}"


def _parse_iso(ts: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _meta(html: str, pattern: re.Pattern[str]) -> str | None:
    m = pattern.search(html)
    return m.group(1) if m else None


def running_build_sha(fetch) -> str | None:
    """The SHA of the actually-running app, read from ``GET /health``. The served
    pages' ``build-sha`` meta is compared to THIS, so an edge/CDN copy from an
    older build (which no date check can catch) fails the canary."""
    r = fetch("/health")
    if r.status != 200:
        return None
    try:
        return str(json.loads(r.text).get("build_sha") or "") or None
    except (ValueError, TypeError):
        return None


def _check_page_freshness(
    path: str, html: str, expected_sha: str | None, now_utc: datetime, failures: list[str]
) -> None:
    """Assert a rendered page is from the running build and rendered recently."""
    page_sha = _meta(html, _BUILD_SHA_RE)
    if page_sha is None:
        failures.append(f"{path}: no <meta name='build-sha'> — un-stamped/old render")
    elif expected_sha and page_sha != expected_sha:
        failures.append(
            f"{path}: build-sha {page_sha!r} != running app {expected_sha!r} "
            f"— STALE render (edge/CDN copy of an older build)"
        )
    ts_raw = _meta(html, _RENDER_TS_RE)
    rendered = _parse_iso(ts_raw) if ts_raw else None
    if rendered is None:
        failures.append(f"{path}: missing/invalid <meta name='render-ts'> ({ts_raw!r})")
        return
    age = now_utc - rendered
    if age > timedelta(hours=RENDER_MAX_AGE_HOURS):
        failures.append(
            f"{path}: rendered {age.total_seconds() / 3600:.1f}h ago "
            f"(> {RENDER_MAX_AGE_HOURS}h) — stale cached copy; render-ts={ts_raw}"
        )


def _sweep_freshness(
    fetch, path: str, expected_sha: str | None, now_utc: datetime, failures: list[str]
) -> None:
    """Fetch ``path`` with EVERY sample UA and freshness-check each — a UA-keyed
    edge cache that freezes one variant fails here even if another UA is fresh."""
    for uaname, ua in SAMPLE_UAS:
        r = fetch(path, ua)
        if r.status != 200:
            failures.append(f"{path} [{uaname}]: expected 200, got {r.status}")
            continue
        _check_page_freshness(f"{path} [{uaname}]", r.text, expected_sha, now_utc, failures)


def _check_gas_freshness(fetch, now_utc: datetime, failures: list[str]) -> None:
    r = fetch("/api/gas")
    if r.status != 200:
        failures.append(f"/api/gas: expected 200, got {r.status}")
        return
    try:
        data = json.loads(r.text)
    except (ValueError, TypeError):
        failures.append("/api/gas: response was not valid JSON")
        return
    if not data.get("cheapest"):
        failures.append("/api/gas: no cheapest station in payload")
    if data.get("is_stale"):
        failures.append(
            f"/api/gas: is_stale=true ({data.get('staleness_label') or 'no label'})"
        )
    iso = data.get("updated_at_iso")
    pulled = _parse_iso(iso) if isinstance(iso, str) else None
    if pulled is None:
        failures.append(f"/api/gas: missing/invalid updated_at_iso ({iso!r})")
        return
    age = now_utc - pulled
    if age > timedelta(hours=GAS_MAX_AGE_HOURS):
        failures.append(
            f"/api/gas: data is {age.total_seconds() / 3600:.1f}h old "
            f"(> {GAS_MAX_AGE_HOURS}h); updated_at={iso}"
        )


def run_checks(fetch, now_utc: datetime) -> list[str]:
    """Return a list of human-readable failure messages (empty == all green).

    ``fetch(path, ua=None) -> Resp`` must NOT auto-follow redirects, so route
    health can distinguish a 3xx from a blank 200. Freshness-critical pages are
    sampled across :data:`SAMPLE_UAS`; the rest use the default UA.
    """
    failures: list[str] = []
    label = phoenix_today_label(now_utc)
    gas_prices: set[str] = set()
    # The running app's SHA — the yardstick for every page's build-sha meta.
    expected_sha = running_build_sha(fetch)
    if expected_sha is None:
        failures.append("/health: could not read running build_sha (SHA match disabled)")

    # 1. Dated-page freshness (the heart of B1) + build-sha/render-ts (same-day
    #    staleness the date label can't catch).
    for path in DATED_PAGES:
        r = fetch(path)
        if r.status != 200:
            failures.append(f"{path}: expected 200, got {r.status}")
            continue
        if label not in r.text:
            failures.append(
                f"{path}: today's date '{label}' not rendered — stale edge copy?"
            )
        if _main_len(r.text) < _MAIN_MIN_CHARS:
            failures.append(f"{path}: <main> is nearly empty ({_main_len(r.text)} chars)")
        # Freshness sampled across ≥3 UA classes (a UA-keyed edge cache freezes one).
        _sweep_freshness(fetch, path, expected_sha, now_utc, failures)
        price = extract_cheapest_gas(r.text)
        if price is not None:
            gas_prices.add(price)

    # 1b. A SPECIFIC-date day view (the exact surface a stale render was served on):
    #     no "today" label to lean on, so build-sha + render-ts are the only guard.
    specific_day = "/events-ui?date=" + now_utc.astimezone(LAKE_HAVASU_TZ).date().isoformat()
    _sweep_freshness(fetch, specific_day, expected_sha, now_utc, failures)

    # 1c. Month-partitioned calendar variants (?cal=YYYY-MM) — a DISTINCT edge-cache
    #     key from bare /calendar. The 2026-07-08 re-audit found a July-1-vintage
    #     /calendar?cal= render frozen at a PoP (no build-sha meta) while bare
    #     /calendar was fresh; the bare-/calendar check above can't see it. Current
    #     + next month; a non-today month carries no date label, so build-sha +
    #     render-ts across UAs are the guard.
    for cal_month in calendar_month_variants(now_utc):
        _sweep_freshness(fetch, f"/calendar?cal={cal_month}", expected_sha, now_utc, failures)

    # 2. One cheapest-gas price everywhere (edge divergence = the '5 prices' bug).
    if len(gas_prices) > 1:
        failures.append(
            f"multiple cheapest-gas prices across pages (edge-cache divergence): "
            f"{sorted(gas_prices)}"
        )

    # 3. Gas data actually fresh.
    _check_gas_freshness(fetch, now_utc, failures)

    # 4. Route health for every nav-reachable URL.
    for path in NAV_PAGES:
        r = fetch(path)
        if r.status != 200:
            failures.append(f"nav {path}: expected 200, got {r.status}")
        elif _main_len(r.text) < _MAIN_MIN_CHARS:
            failures.append(f"nav {path}: 200 but <main> nearly empty ({_main_len(r.text)} chars)")
    for path in NAV_REDIRECTS:
        r = fetch(path)
        ok = r.status in _REDIRECT_CODES or (
            r.status == 200 and _main_len(r.text) >= _MAIN_MIN_CHARS
        )
        if not ok:
            failures.append(f"nav {path}: unhealthy status {r.status}")

    return failures


# ── real-network wiring (not exercised by unit tests) ──────────────────────────
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # type: ignore[override]
        return None  # surface the 3xx instead of following it


def _live_fetcher(base: str):
    opener = urllib.request.build_opener(_NoRedirect)

    def fetch(path: str, ua: str | None = None) -> Resp:
        req = urllib.request.Request(  # noqa: S310 — fixed https base, bot/sample UA
            base + path, headers={"User-Agent": ua or BOT_UA, "Cookie": ""}
        )
        try:
            with opener.open(req, timeout=30) as resp:
                return Resp(resp.status, resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            # 3xx (redirects suppressed) and 4xx/5xx land here.
            body = exc.read().decode("utf-8", "replace") if exc.code < 400 else ""
            return Resp(exc.code, body, exc.headers.get("Location"))
        except (urllib.error.URLError, TimeoutError) as exc:  # pragma: no cover
            return Resp(0, f"<transport error: {exc}>")

    return fetch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=DEFAULT_BASE, help="Origin to probe.")
    args = parser.parse_args(argv)

    now_utc = datetime.now(UTC)
    failures = run_checks(_live_fetcher(args.base.rstrip("/")), now_utc)

    label = phoenix_today_label(now_utc)
    if failures:
        print(f"CANARY FAIL ({args.base}) -- Phoenix today = {label}:", file=sys.stderr)
        for f in failures:
            print(f"  [FAIL] {f}", file=sys.stderr)
        return 1
    print(f"CANARY OK ({args.base}) -- all fresh; Phoenix today = {label}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
