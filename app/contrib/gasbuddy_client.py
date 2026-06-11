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
similar unblockers terminate TLS and re-encrypt with their own cert).

ScraperAPI specifics (``proxy-server.scraperapi.com``):
  - ``/home`` CSRF fetch: httpx with ``session_number`` only (standard pool).
    ``render=true`` fallback when the token is missing (GET-only).
  - GraphQL POST: ``requests`` proxy-port with ``premium=true`` and
    ``keep_headers=true`` in the username. httpx does not reliably forward
    username params on POST; ``ultra_premium`` discards custom headers.
  - ``session_number`` pins the same proxy IP across /home and GraphQL.
  - Non-ScraperAPI proxies use httpx with ``verify=False`` throughout.

ASCII-only by project convention.
"""

from __future__ import annotations

import logging
import os
import random
import re
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
import requests
import urllib3

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://www.gasbuddy.com/graphql"
PRIME_URL = "https://www.gasbuddy.com/home"
REQUEST_TIMEOUT = 30.0
# ScraperAPI / unblocker round-trips are slow; keep below their ~70s ceiling.
PROXY_REQUEST_TIMEOUT = 90.0
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
    "Sec-Fetch-Dest": "",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Priority": "u=0",
    "apollo-require-preflight": "true",
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


def _is_scraperapi_proxy(proxy: str) -> bool:
    return "scraperapi.com" in (urlparse(proxy).hostname or "").lower()


def _parse_scraperapi_username(user: str) -> dict[str, str]:
    """Parse ``scraperapi.k=v.k2=v2`` username params into a dict."""
    if user in ("", "scraperapi"):
        return {}
    if not user.startswith("scraperapi."):
        return {}
    params: dict[str, str] = {}
    for part in user[len("scraperapi.") :].split("."):
        if "=" in part:
            key, val = part.split("=", 1)
            params[key] = val
    return params


def _rebuild_proxy_url(proxy: str, username: str) -> str:
    parsed = urlparse(proxy)
    password = parsed.password or ""
    auth = f"{username}:{password}@" if password else f"{username}@"
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{auth}{parsed.hostname}{port}"
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
    )


def _prepare_scraperapi_proxy(
    proxy: str,
    *,
    session_number: str | None = None,
    premium: bool = False,
    keep_headers: bool = False,
    render: bool = False,
) -> str:
    """Build an httpx/requests proxy URL with ScraperAPI username params."""
    params = _parse_scraperapi_username(urlparse(proxy).username or "")
    sid = session_number or params.get("session_number") or str(random.randint(1, 9_999_999))
    ordered: list[tuple[str, str]] = []
    if premium and "premium" not in params and "ultra_premium" not in params:
        ordered.append(("premium", "true"))
    if keep_headers and "keep_headers" not in params:
        ordered.append(("keep_headers", "true"))
    ordered.append(("session_number", sid))
    if render:
        ordered.append(("render", "true"))
    for key, val in params.items():
        if key in {k for k, _ in ordered}:
            continue
        ordered.append((key, val))
    parts = [f"{key}={val}" for key, val in ordered]
    username = f"scraperapi.{'.'.join(parts)}" if parts else "scraperapi"
    return _rebuild_proxy_url(proxy, username)


def _scraperapi_requests_proxies(proxy_url: str) -> dict[str, str]:
    """``requests`` proxies dict (http key only -- ScraperAPI docs pattern)."""
    return {"http": proxy_url}


def _fetch_csrf_token_scraperapi(
    proxy: str, *, session_number: str, render: bool = False
) -> str | None:
    """GET /home via httpx on the standard ScraperAPI pool (no premium tier)."""
    home_proxy = _prepare_scraperapi_proxy(
        proxy, session_number=session_number, premium=False, render=render
    )
    with _build_client(proxy=home_proxy) as client:
        return _fetch_csrf_token(client)


def _graphql_headers(token: str | None) -> dict[str, str]:
    headers = dict(DEFAULT_HEADERS)
    if token:
        headers["gbcsrf"] = token
        headers["x-apollo-operation-name"] = "LocationBySearchTerm"
        headers["Cookie"] = f"gbcsrf={token}"
    return headers


def _fetch_stations_scraperapi(
    proxy: str,
    zips: tuple[str, ...],
    *,
    session_number: str,
    token: str | None,
) -> list[dict[str, Any]]:
    post_proxy = _prepare_scraperapi_proxy(
        proxy,
        session_number=session_number,
        premium=True,
        keep_headers=True,
        render=False,
    )
    logger.debug("ScraperAPI GraphQL request prepared (session=%s)", session_number)
    proxies = _scraperapi_requests_proxies(post_proxy)
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    headers = _graphql_headers(token)
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for zip_code in zips:
        cursor: str | None = None
        for _ in range(MAX_PAGES_PER_ZIP):
            payload = {
                "operationName": "LocationBySearchTerm",
                "query": LOCATION_QUERY_PRICES,
                "variables": {"maxAge": 0, "search": zip_code, "cursor": cursor},
            }
            try:
                resp = requests.post(
                    GRAPHQL_URL,
                    json=payload,
                    headers=headers,
                    proxies=proxies,
                    verify=False,
                    timeout=PROXY_REQUEST_TIMEOUT,
                )
            except requests.RequestException as exc:  # pragma: no cover - network dependent
                logger.warning("GasBuddy fetch failed for %s: %s", zip_code, exc)
                break
            if resp.status_code >= 400:
                logger.warning(
                    "GasBuddy graphql HTTP %s for %s: %s",
                    resp.status_code,
                    zip_code,
                    (resp.text or "")[:300],
                )
            try:
                resp.raise_for_status()
            except requests.HTTPError as exc:
                logger.warning("GasBuddy fetch failed for %s: %s", zip_code, exc)
                break
            try:
                body = resp.json()
            except ValueError:
                break
            if not isinstance(body, dict):
                break
            if body.get("errors"):
                logger.warning("GasBuddy graphql errors for %s: %s", zip_code, body["errors"])
            data = body.get("data") or {}
            loc = (data.get("locationBySearchTerm") or {}) if isinstance(data, dict) else {}
            stations = (loc.get("stations") or {}) if isinstance(loc, dict) else {}
            results = stations.get("results") if isinstance(stations, dict) else None
            if isinstance(results, list):
                for st in results:
                    if not isinstance(st, dict):
                        continue
                    sid = str(st.get("id") or "")
                    if sid and sid in seen:
                        continue
                    if sid:
                        seen.add(sid)
                    merged.append(st)
            nxt = stations.get("cursor") if isinstance(stations, dict) else None
            cursor = nxt.get("next") if isinstance(nxt, dict) else None
            if not cursor:
                break
    return merged


def _fetch_lhc_stations_scraperapi(proxy: str, zips: tuple[str, ...]) -> list[dict[str, Any]]:
    """ScraperAPI: httpx /home CSRF + requests premium POST with keep_headers."""
    session = str(random.randint(1, 9_999_999))
    token = _fetch_csrf_token_scraperapi(proxy, session_number=session, render=False)
    if not token:
        logger.info(
            "GasBuddy /home CSRF fetch failed via ScraperAPI; "
            "retrying /home with render=true (same session)"
        )
        token = _fetch_csrf_token_scraperapi(proxy, session_number=session, render=True)
    if not token:
        logger.warning("GasBuddy CSRF token unavailable via ScraperAPI; GraphQL will likely fail.")
    return _fetch_stations_scraperapi(proxy, zips, session_number=session, token=token)


def _apply_csrf(client: httpx.Client, token: str) -> None:
    """Attach GasBuddy CSRF token as header + cookie for GraphQL POSTs."""
    client.headers["gbcsrf"] = token
    client.headers["x-apollo-operation-name"] = "LocationBySearchTerm"
    client.cookies.set("gbcsrf", token, domain="www.gasbuddy.com")


def _build_client(*, proxy: str | None = None, timeout: float | None = None) -> httpx.Client:
    """Construct an httpx client, routing through the unblocker proxy if set."""
    proxy = _proxy_url() if proxy is None else proxy
    effective_timeout = (
        timeout if timeout is not None else (PROXY_REQUEST_TIMEOUT if proxy else REQUEST_TIMEOUT)
    )
    kwargs: dict[str, Any] = {
        "headers": dict(DEFAULT_HEADERS),
        "timeout": effective_timeout,
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
        resp = client.get(PRIME_URL)
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
        resp = client.post(GRAPHQL_URL, json=payload)
        if resp.status_code >= 400:
            logger.warning(
                "GasBuddy graphql HTTP %s for %s: %s",
                resp.status_code,
                search,
                (resp.text or "")[:300],
            )
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
    client: httpx.Client, zips: tuple[str, ...], *, token: str | None = None
) -> list[dict[str, Any]]:
    """Fetch + de-dupe raw GasBuddy stations for one httpx client session."""
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    if token is None:
        token = _fetch_csrf_token(client)
    if token:
        _apply_csrf(client, token)
    for zip_code in zips:
        try:
            results = fetch_stations_for_search(client, zip_code)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 403) and token:
                token = _fetch_csrf_token(client)
                if token:
                    _apply_csrf(client, token)
                    try:
                        results = fetch_stations_for_search(client, zip_code)
                    except httpx.HTTPError as retry_exc:
                        logger.warning(
                            "GasBuddy fetch failed for %s after CSRF refresh: %s",
                            zip_code,
                            retry_exc,
                        )
                        continue
                else:
                    logger.warning("GasBuddy fetch failed for %s: %s", zip_code, exc)
                    continue
            else:
                logger.warning("GasBuddy fetch failed for %s: %s", zip_code, exc)
                continue
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
    """
    proxy = _proxy_url()
    if proxy and _is_scraperapi_proxy(proxy):
        merged = _fetch_lhc_stations_scraperapi(proxy, zips)
    else:
        with _build_client(proxy=proxy) as client:
            merged = _fetch_lhc_stations_with_client(client, zips)

    logger.info("GasBuddy returned %d unique stations across %d ZIPs", len(merged), len(zips))
    return merged
