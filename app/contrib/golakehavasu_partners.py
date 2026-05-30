"""
golakehavasu.com partner directory -- sitemap discovery + listing HTML parsing.

Partner detail pages (``/directory/<slug>/``) describe a local business. Unlike
the event pages, the page's JSON-LD is just the CVB's own Organization identity
(``Go Lake Havasu``) -- NOT the partner -- so partner data is parsed from the
DOM: H1 name, the "Contact" address block (street / city / phone), the partner
website link, and lat/lon from the Google static-map markers.

Each listing maps to an :class:`~app.contrib.ingest_base.EntityPayload` with
``source="go_lake_havasu"`` and is routed through
:func:`~app.contrib.ingest_reconciler.reconcile_hit` by the loader so a partner
that is already a Google Places provider UPDATES the existing row (fills CVB
gaps) instead of creating a duplicate. Maximum-overlap surface -- the reconciler
is what keeps it clean.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.contrib.golakehavasu import (
    SITEMAP_HTTP_TIMEOUT,
    SITEMAP_INDEX_URL,
    _headers,
    _http_get_text,
)
from app.contrib.ingest_base import EntityPayload

# Partner child sitemaps contain this substring (there are two: p1 + p2).
PARTNERS_SITEMAP_SUBSTR = "partnerDirectory"
SOURCE_NAME = "go_lake_havasu"

PARTNER_PAGE_HTTP_TIMEOUT = httpx.Timeout(60.0, connect=20.0)

_LATLON_RE = re.compile(r"markers=color:[^\"'&]*?%7C(-?\d+\.\d+),(-?\d+\.\d+)")
_ZIP_LINE_RE = re.compile(r",\s*AZ\s+\d{5}")
_PHONE_RE = re.compile(r"\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}")
_CONTACT_LABELS = frozenset({"contact", "location", "address"})
_WEBSITE_LABELS = frozenset({"website", "visit website", "go to website"})


@dataclass
class PartnerListing:
    """Normalized business listing parsed from a golakehavasu directory page."""

    name: str
    url: str
    address: str | None
    lat: float | None
    lng: float | None
    phone: str | None
    website: str | None
    description: str | None
    raw: dict[str, Any] = field(default_factory=dict)


def fetch_partner_sitemap_urls(*, client: httpx.Client | None = None) -> list[str]:
    """Load the sitemap index, follow every ``partnerDirectory`` child, and
    return all partner ``<url><loc>`` (no filtering)."""
    if client is None:
        with httpx.Client(
            timeout=SITEMAP_HTTP_TIMEOUT,
            headers=_headers(),
            follow_redirects=True,
        ) as c:
            return fetch_partner_sitemap_urls(client=c)

    xml_index = _http_get_text(SITEMAP_INDEX_URL, client, timeout=SITEMAP_HTTP_TIMEOUT)
    root = ET.fromstring(xml_index)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    sub_locs: list[str] = []
    for sm in root.findall("sm:sitemap", ns):
        loc = sm.find("sm:loc", ns)
        if loc is not None and loc.text and PARTNERS_SITEMAP_SUBSTR in loc.text:
            sub_locs.append(loc.text.strip())

    urls: list[str] = []
    seen: set[str] = set()
    for sub in sub_locs:
        if sub in seen:
            continue
        seen.add(sub)
        xml_page = _http_get_text(sub, client, timeout=SITEMAP_HTTP_TIMEOUT)
        subroot = ET.fromstring(xml_page)
        for url_el in subroot.findall("sm:url", ns):
            loc = url_el.find("sm:loc", ns)
            if loc is not None and loc.text:
                urls.append(loc.text.strip())
    return urls


def _contact_block(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    """Parse the DOM contact block -> (full_address, phone).

    Shape (verified): ['Contact', <street>, '<city>, AZ <zip>', '<phone?>'].
    """
    zip_node = soup.find(string=_ZIP_LINE_RE)
    if not zip_node:
        return None, None
    container: Any = zip_node.parent
    for _ in range(3):
        if container is not None and container.parent is not None:
            container = container.parent
    if container is None:
        return None, None
    lines = [re.sub(r"\s+", " ", s).strip() for s in container.stripped_strings]
    lines = [ln for ln in lines if ln and ln.lower() not in _CONTACT_LABELS]
    city_idx = next((i for i, ln in enumerate(lines) if _ZIP_LINE_RE.search(ln)), None)
    if city_idx is None:
        return None, None
    city_line = lines[city_idx]
    street = lines[city_idx - 1] if city_idx - 1 >= 0 else None
    if street and _PHONE_RE.fullmatch(street):
        street = None
    phone = None
    for ln in lines[city_idx + 1 :]:
        if _PHONE_RE.search(ln):
            phone = _PHONE_RE.search(ln).group(0)
            break
    parts = [p for p in (street, city_line) if p]
    address = ", ".join(parts) if parts else None
    return address, phone


def _website(soup: BeautifulSoup) -> str | None:
    for a in soup.find_all("a", href=True):
        label = a.get_text(" ", strip=True).lower()
        if label in _WEBSITE_LABELS:
            href = (a.get("href") or "").strip()
            if href and not href.startswith(("#", "javascript:")):
                if "golakehavasu.com" not in href:
                    return href
    return None


def _description(soup: BeautifulSoup) -> str | None:
    heading = soup.find(
        lambda tag: (
            tag.name in ("h2", "h3", "h4")
            and tag.get_text(strip=True).lower() in ("overview", "about", "description")
        )
    )
    if heading:
        chunks: list[str] = []
        for sib in heading.find_all_next(["p", "li"], limit=8):
            t = sib.get_text(" ", strip=True)
            if t:
                chunks.append(t)
        if chunks:
            return "\n\n".join(chunks)
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return str(meta["content"]).strip() or None
    return None


def _latlon(html: str) -> tuple[float | None, float | None]:
    m = _LATLON_RE.search(html)
    if not m:
        return None, None
    try:
        return float(m.group(1)), float(m.group(2))
    except (TypeError, ValueError):
        return None, None


def fetch_and_parse_partner(
    url: str,
    *,
    client: httpx.Client | None = None,
) -> PartnerListing | None:
    """Fetch one partner directory page and parse it. ``None`` if unnamed."""
    if client is None:
        with httpx.Client(
            timeout=PARTNER_PAGE_HTTP_TIMEOUT,
            headers=_headers(),
            follow_redirects=True,
        ) as c:
            return fetch_and_parse_partner(url, client=c)

    html = _http_get_text(url, client, timeout=PARTNER_PAGE_HTTP_TIMEOUT)
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    name = h1.get_text(" ", strip=True) if h1 else ""
    if not name:
        return None
    address, phone = _contact_block(soup)
    lat, lng = _latlon(html)
    return PartnerListing(
        name=name[:300],
        url=url.strip(),
        address=address,
        lat=lat,
        lng=lng,
        phone=phone,
        website=_website(soup),
        description=_description(soup),
    )


def partner_to_entity_payload(
    listing: PartnerListing,
    *,
    category_slug: str,
) -> EntityPayload:
    """Map a :class:`PartnerListing` to a source-agnostic :class:`EntityPayload`."""
    return EntityPayload(
        name=listing.name,
        entity_type="place",
        lat=listing.lat,
        lng=listing.lng,
        address=listing.address,
        phone=listing.phone,
        website=listing.website,
        description=listing.description,
        category_slug=category_slug,
        google_place_id=None,
        source=SOURCE_NAME,
    )
