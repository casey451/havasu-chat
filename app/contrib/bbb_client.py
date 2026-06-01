"""Better Business Bureau Lake Havasu City accredited-business client (V1.5
Trust-Signal Verifier Bundle wave 4, ticket #23).

§3.1 probe (2026-05-24): the categories index at
``https://www.bbb.org/us/az/lake-havasu-city/categories`` returns 200 via
httpx + BeautifulSoup. Accredited listing pages at
``/category/<slug>/accredited`` may return 403 / Cloudflare from automation
IPs; those slugs are skipped so the verifier can continue (functional-but-inert
when all slugs block).

Parsed fields mirror the wave-3 bulk-registry shape: each row includes
``business_id``, ``business_name``, ``profile_url``, and optional
``accreditation_status`` / ``rating`` when present in listing HTML or profile
JSON-LD.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Final
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BBB_LHC_BASE: Final[str] = "https://www.bbb.org/us/az/lake-havasu-city"
BBB_CATEGORIES_URL: Final[str] = f"{BBB_LHC_BASE}/categories"
CITY_PATH_VARIANTS: Final[tuple[str, ...]] = (
    "/us/az/lake-havasu-city/",
    "/us/az/lk-havasu-cty/",
)
PROFILE_ID_RE: Final[re.Pattern[str]] = re.compile(r"/profile/[^/]+/[^/]+-1126-(\d+)(?:/|$)", re.I)
CATEGORY_SLUG_RE: Final[re.Pattern[str]] = re.compile(r"/category/([^/]+)/?", re.I)

# Shopping-essentials–aligned BBB category slugs (subset walk when set).
SHOPPING_ESSENTIALS_CATEGORY_SLUGS: Final[frozenset[str]] = frozenset(
    {
        "convenience-store",
        "department-stores",
        "discount-stores",
        "drug-stores-and-pharmacies",
        "electronics-and-technology",
        "furniture-stores",
        "gift-shop",
        "grocery-store",
        "hardware-store",
        "home-improvement-stores",
        "jewelry-stores",
        "office-supplies",
        "sporting-goods",
        "variety-stores",
    }
)


def _browser_headers(*, referer: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def _is_blocked_response(resp: httpx.Response) -> bool:
    if resp.status_code in {403, 429, 503}:
        return True
    text = resp.text[:2000].lower()
    return "just a moment" in text or "cf-chl" in text or "cloudflare" in text


def fetch_bbb_category_slugs(client: httpx.Client) -> list[str]:
    """Return BBB category slugs from the Lake Havasu City categories index."""
    resp = client.get(BBB_CATEGORIES_URL, headers=_browser_headers(), timeout=60.0)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    slugs: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "/category/" not in href:
            continue
        match = CATEGORY_SLUG_RE.search(href)
        if match:
            slugs.add(match.group(1).lower())
    out = sorted(slugs)
    logger.info(
        "bbb_client.categories_index",
        extra={"url": BBB_CATEGORIES_URL, "total": len(out)},
    )
    return out


def _parse_accredited_listing_html(html: str, *, category_slug: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "/profile/" not in href:
            continue
        full_url = urljoin(BBB_CATEGORIES_URL, href)
        match = PROFILE_ID_RE.search(full_url)
        if not match:
            continue
        business_id = match.group(1)
        if business_id in seen_ids:
            continue
        seen_ids.add(business_id)
        name = anchor.get_text(" ", strip=True)
        if not name:
            continue
        row: dict[str, Any] = {
            "business_id": business_id,
            "business_name": name,
            "profile_url": full_url,
            "category_slug": category_slug,
        }
        parent = anchor.find_parent(["div", "li", "article"])
        if parent is not None:
            rating_el = parent.find(string=re.compile(r"^[A-F][+-]?$"))
            if rating_el:
                row["rating"] = str(rating_el).strip()
            if parent.find(string=re.compile(r"accredited", re.I)):
                row["accreditation_status"] = "Accredited"
        rows.append(row)
    return rows


def _enrich_from_profile_jsonld(client: httpx.Client, row: dict[str, Any]) -> None:
    profile_url = row.get("profile_url")
    if not profile_url:
        return
    try:
        resp = client.get(
            str(profile_url),
            headers=_browser_headers(referer=BBB_CATEGORIES_URL),
            timeout=45.0,
        )
    except httpx.HTTPError:
        return
    if _is_blocked_response(resp):
        return
    if resp.status_code != 200:
        return
    soup = BeautifulSoup(resp.text, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") not in {"LocalBusiness", "Organization"}:
                continue
            if item.get("name") and not row.get("business_name"):
                row["business_name"] = str(item["name"]).strip()
            agg = item.get("aggregateRating")
            if isinstance(agg, dict) and agg.get("ratingValue"):
                row["rating"] = str(agg["ratingValue"]).strip()
            if item.get("url"):
                row["profile_url"] = str(item["url"]).strip()
            row.setdefault("accreditation_status", "Accredited")
            return


def fetch_bbb_businesses(
    client: httpx.Client,
    *,
    category_slugs: list[str] | None = None,
    enrich_profiles: bool = False,
    polite_delay_s: float = 0.5,
    max_blocked_without_rows: int = 10,
) -> list[dict[str, Any]]:
    """Return accredited BBB businesses for Lake Havasu City.

      Walks ``/category/<slug>/accredited`` pages. Slugs blocked by Cloudflare /
      HTTP 403 are skipped; returns partial rows when some slugs succeed, or
    ``[]`` when every slug blocks (functional-but-inert path).
    """
    all_slugs = category_slugs or fetch_bbb_category_slugs(client)
    if category_slugs is None:
        mapped = [s for s in all_slugs if s in SHOPPING_ESSENTIALS_CATEGORY_SLUGS]
        if mapped:
            all_slugs = mapped

    rows: list[dict[str, Any]] = []
    blocked = 0
    consecutive_blocked = 0
    for slug in all_slugs:
        url = f"{BBB_LHC_BASE}/category/{slug}/accredited"
        try:
            resp = client.get(
                url,
                headers=_browser_headers(referer=BBB_CATEGORIES_URL),
                timeout=60.0,
            )
        except httpx.HTTPError:
            logger.warning("bbb_client.accredited_fetch_error", extra={"slug": slug, "url": url})
            blocked += 1
            consecutive_blocked += 1
            time.sleep(polite_delay_s)
            if not rows and consecutive_blocked >= max_blocked_without_rows:
                logger.info(
                    "bbb_client.early_abort_all_blocked",
                    extra={"blocked_slugs": blocked, "slugs_walked": blocked},
                )
                break
            continue

        if _is_blocked_response(resp):
            logger.info(
                "bbb_client.accredited_blocked",
                extra={"slug": slug, "status": resp.status_code, "url": url},
            )
            blocked += 1
            consecutive_blocked += 1
            time.sleep(polite_delay_s)
            if not rows and consecutive_blocked >= max_blocked_without_rows:
                logger.info(
                    "bbb_client.early_abort_all_blocked",
                    extra={"blocked_slugs": blocked, "slugs_walked": blocked},
                )
                break
            continue

        consecutive_blocked = 0

        resp.raise_for_status()
        slug_rows = _parse_accredited_listing_html(resp.text, category_slug=slug)
        rows.extend(slug_rows)
        logger.debug(
            "bbb_client.accredited_parsed",
            extra={"slug": slug, "rows": len(slug_rows)},
        )
        time.sleep(polite_delay_s)

    if enrich_profiles and rows:
        for row in rows[:50]:
            _enrich_from_profile_jsonld(client, row)
            time.sleep(polite_delay_s)

    logger.info(
        "bbb_client.fetch_complete",
        extra={
            "slugs_walked": len(all_slugs),
            "blocked_slugs": blocked,
            "total": len(rows),
        },
    )
    return rows
