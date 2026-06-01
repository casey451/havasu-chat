"""GasBuddy GraphQL client for Lake Havasu City per-station gas prices.

Primary source for the gas-prices feed (see ``app/contrib/gas_prices.py``).

GasBuddy exposes an unofficial GraphQL endpoint at ``/graphql`` -- the same
one their own site uses. The request shape mirrors the open-source
``py-gasbuddy`` library (firstof9/py-gasbuddy, v0.7.0):

  1. GasBuddy's Apollo server enforces CSRF prevention: a JSON POST is
     rejected with HTTP 400 unless it carries ``apollo-require-preflight:
     true`` AND a ``gbcsrf`` token. The token is embedded in the /home HTML
     as ``window.gbcsrf = "<token>"`` -- we GET /home and regex it out.
  2. The price-bearing query is ``LOCATION_QUERY_PRICES`` (operation
     ``LocationBySearchTerm``) searched per ZIP with ``priority: "locality"``.

Reliability: from a datacenter IP (Railway / GitHub Actions) -- and often
from residential IPs too -- Cloudflare challenges the /home GET, so the token
cannot be scraped and the feed falls back to Google. Set
``GAS_SCRAPE_PROXY_URL`` (ScraperAPI proxy port, Bright Data Web Unlocker,
Nimble, etc. -- ``http://user:pass@host:port``) and every request routes
through it so both the token fetch and the POST get past Cloudflare.

Proxied fetches use ``verify=False`` on the httpx client only (ScraperAPI and
similar unblockers terminate TLS and re-encrypt with their own cert). When
GasBuddy still returns zero stations via a ScraperAPI proxy, we retry once
with ``scraperapi.render=true`` in the proxy username (JS rendering).

ASCII-only by project convention.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://www.gasbuddy.com/graphql"
PRIME_URL = "https://www.gasbuddy.com/home"
REQUEST_TIMEOUT = 30.0
MAX_PAGES_PER_ZIP = 5

# Lake Havasu City ZIP codes searched on GasBuddy. 86405 is PO-box only and is
# omitted; 86403 / 86404 / 86406 cover the populated area.
LHC_ZIPS: tuple[str, ...] = ("86403", "86404", "86406")

_CSRF_PATTERN = re.compile(r'window\.gbcsrf\s*=\s*(["\'])(.*?)\1')

# Headers GasBuddy's Apollo server requires (from py-gasbuddy DEFAULT_HEADERS).
# ``apollo-require-preflight: true`` is the key one -- without it the POST is
# blocked as CSRF with HTTP 400.
DEFAULT_HEADERS: dict[str, str] = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "apollo-require-preflight": "true",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Origin": "https://www.gasbuddy.com",
    "Referer": PRIME_URL,
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    ),
}

# The price-bearing query (py-gasbuddy LOCATION_QUERY_PRICES). priority:
# "locality" keeps results tight to the searched town.
LOCATION_QUERY_PRICES = """
query LocationBySearchTerm($brandId: Int, $cursor: String, $fuel: Int, $lat: Float, $lng: Float, $maxAge: Int, $search: String) {
  locationBySearchTerm(lat: $lat, lng: $lng, search: $search, priority: "locality") {
    stations(brandId: $brandId, cursor: $cursor, fuel: $fuel, lat: $lat, lng: $lng, maxAge: $maxAge, priority: "locality") {
      cursor { next }
      results {
        address { line1 line2 locality postalCode region }
        brands { brandId name }
        distance
        id
        latitude
        longitude
        name
        prices {
          cash { nickname postedTime price }
          credit { nickname postedTime price }
          fuelProduct
        }
      }
    }
  }
}
""".strip()


def _proxy_url() -> str | None:
    val = (os.environ.get("GAS_SCRAPE_PROXY_URL") or "").strip()
    return val or None


def _scraperapi_render_proxy(proxy: str) -> str | None:
    """Return a ScraperAPI proxy URL with ``render=true``, or None if N/A.

    ScraperAPI encodes API params in the proxy username (e.g.
    ``scraperapi.render=true:API_KEY@proxy-server.scraperapi.com:8001``).
    """
    parsed = urlparse(proxy)
    host = (parsed.hostname or "").lower()
    if "scraperapi.com" not in host:
        return None
    user = parsed.username or ""
    if not user.startswith("scraperapi"):
        return None
    if "render=true" in user:
        return None
    if user == "scraperapi":
        new_user = "scraperapi.render=true"
    elif user.startswith("scraperapi."):
        new_user = f"scraperapi.render=true.{user[len('scraperapi.') :]}"
    else:
        return None
    password = parsed.password or ""
    auth = f"{new_user}:{password}@" if password else f"{new_user}@"
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{auth}{parsed.hostname}{port}"
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
    )


def _build_client(*, proxy: str | None = None) -> httpx.Client:
    """Construct an httpx client, routing through the unblocker proxy if set."""
    proxy = _proxy_url() if proxy is None else proxy
    kwargs: dict[str, Any] = {
        "headers": dict(DEFAULT_HEADERS),
        "timeout": REQUEST_TIMEOUT,
        "follow_redirects": True,
    }
    if proxy:
        # ScraperAPI / similar proxies MITM TLS; cert won't chain to a public CA.
        kwargs["verify"] = False
        # httpx >=0.26 uses ``proxy=``; older releases use ``proxies=``.
        try:
            return httpx.Client(proxy=proxy, **kwargs)
        except TypeError:
            return httpx.Client(proxies=proxy, **kwargs)
    return httpx.Client(**kwargs)


def _fetch_csrf_token(client: httpx.Client) -> str | None:
    """GET /home and extract the ``window.gbcsrf`` token from the HTML.

    Returns None when Cloudflare challenges the GET (no token in the body) --
    the caller then proceeds tokenless (works behind an unblocker proxy that
    returns the real page; otherwise the POST will 400 and we fall back).
    """
    try:
        resp = client.get(PRIME_URL, timeout=REQUEST_TIMEOUT)
    except httpx.HTTPError as exc:  # pragma: no cover - network dependent
        logger.warning("GasBuddy /home request failed: %s", exc)
        return None
    if resp.status_code != 200:
        logger.warning(
            "GasBuddy /home returned HTTP %s (Cloudflare challenge likely); "
            "no CSRF token. Set GAS_SCRAPE_PROXY_URL to an unblocker proxy.",
            resp.status_code,
        )
        return None
    match = _CSRF_PATTERN.search(resp.text)
    if not match:
        logger.warning("GasBuddy /home loaded but window.gbcsrf not found.")
        return None
    token = match.group(2)
    logger.debug("GasBuddy CSRF token acquired (len=%d)", len(token))
    return token


def fetch_stations_for_search(
    client: httpx.Client, search: str, *, max_pages: int = MAX_PAGES_PER_ZIP
) -> list[dict[str, Any]]:
    """POST LocationBySearchTerm for one ZIP, following cursor pagination.

    Returns the raw ``results`` list (one dict per station). Raises
    ``httpx.HTTPError`` on a transport/HTTP error so the orchestrator can
    record the failure.
    """
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(max_pages):
        payload = {
            "operationName": "LocationBySearchTerm",
            "query": LOCATION_QUERY_PRICES,
            "variables": {"maxAge": 0, "search": search, "cursor": cursor},
        }
        resp = client.post(GRAPHQL_URL, json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            break
        if body.get("errors"):
            logger.warning("GasBuddy graphql errors for %s: %s", search, body["errors"])
        data = body.get("data") or {}
        loc = (data.get("locationBySearchTerm") or {}) if isinstance(data, dict) else {}
        stations = (loc.get("stations") or {}) if isinstance(loc, dict) else {}
        results = stations.get("results") if isinstance(stations, dict) else None
        if isinstance(results, list):
            out.extend(r for r in results if isinstance(r, dict))
        nxt = stations.get("cursor") if isinstance(stations, dict) else None
        cursor = nxt.get("next") if isinstance(nxt, dict) else None
        if not cursor:
            break
    return out


def _fetch_lhc_stations_with_client(
    client: httpx.Client, zips: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Fetch + de-dupe raw GasBuddy stations for one httpx client session."""
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    token = _fetch_csrf_token(client)
    if token:
        client.headers["gbcsrf"] = token
    for zip_code in zips:
        try:
            results = fetch_stations_for_search(client, zip_code)
        except httpx.HTTPError as exc:  # pragma: no cover - network dependent
            logger.warning("GasBuddy fetch failed for %s: %s", zip_code, exc)
            continue
        for st in results:
            sid = str(st.get("id") or "")
            if sid and sid in seen:
                continue
            if sid:
                seen.add(sid)
            merged.append(st)
    return merged


def fetch_lhc_stations(zips: tuple[str, ...] = LHC_ZIPS) -> list[dict[str, Any]]:
    """Fetch + de-duplicate raw GasBuddy stations across all LHC ZIPs.

    De-dupes on GasBuddy station ``id`` (the same station appears in more than
    one ZIP search because GasBuddy returns a radius around the term).

    When ``GAS_SCRAPE_PROXY_URL`` points at ScraperAPI and the first pass
    returns zero stations, retries once with ``render=true`` (JS rendering).
    """
    proxy = _proxy_url()
    with _build_client(proxy=proxy) as client:
        merged = _fetch_lhc_stations_with_client(client, zips)

    if not merged and proxy:
        render_proxy = _scraperapi_render_proxy(proxy)
        if render_proxy:
            logger.info(
                "GasBuddy returned 0 stations via ScraperAPI proxy; retrying with render=true"
            )
            with _build_client(proxy=render_proxy) as client:
                merged = _fetch_lhc_stations_with_client(client, zips)

    logger.info("GasBuddy returned %d unique stations across %d ZIPs", len(merged), len(zips))
    return merged
