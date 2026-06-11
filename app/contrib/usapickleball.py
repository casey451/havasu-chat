"""USA Pickleball / Places2Play court-finder scrape: fetch + parse + payload map.

Mirrors :mod:`app.contrib.golakehavasu_partners`: pure parse helpers operate on
fetched HTML strings (so they unit-test against fixtures with no network), and a
thin fetch layer wraps them with an injectable ``httpx.Client``. The loader
(:mod:`scripts.usapickleball_load`) owns persistence + reconcile hand-off.

**Data source.** ``places2play.org`` is USA Pickleball's official court finder.
Its map JS guards an ``/api/get`` endpoint behind a per-session seed handshake
that no longer issues seeds to anonymous clients, so we use the server-rendered
search results page instead: ``GET /search?q=<query>`` returns a full HTML table
(Place | Address | City | Courts | Info) with everything we need except
coordinates. Per-place ``lat``/``lng`` live on the ``/place?id=<id>`` detail page
as Open Graph ``place:location:*`` meta, fetched as an enrichment step.

Records map to ``source="usapickleball"`` payloads under the ``racquet-sports``
subcategory; the loader resolves the Tier-1 ``classes-sports-recreation`` slug to
``Provider.category_id``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from app.contrib.ingest_base import EntityPayload

BASE_URL = "https://www.places2play.org"
USER_AGENT = "Hava/0.1 (+https://github.com/casey451/havasu-chat)"
REQUEST_TIMEOUT = httpx.Timeout(45.0, connect=20.0)

SOURCE_NAME = "usapickleball"
# Tier-1 catalog slug (resolved to Provider.category_id by the loader). Pickleball
# lives under the Sports/Fitness bucket whose public page is classes-sports-recreation.
DEFAULT_CATEGORY_SLUG = "classes-sports-recreation"
# Second-level Provider.subcategory (see app/categories/subcategories.py).
SUBCATEGORY = "racquet-sports"
# Legacy Provider.category string; derive_subcategory maps it back to SUBCATEGORY
# so the subcategory backfill stays idempotent.
LEGACY_CATEGORY = "pickleball"

_PLACE_ID_RE = re.compile(r"/place\?id=(\d+)")
_COURTS_RE = re.compile(r"In:\s*(\d+)\s*Out:\s*(\d+)", re.I)
_LAT_RE = re.compile(r'place:location:latitude"\s+content="(-?\d+\.\d+)"')
_LNG_RE = re.compile(r'place:location:longitude"\s+content="(-?\d+\.\d+)"')
_ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b")


@dataclass
class PickleballPlace:
    """One court/facility listing parsed from a Places2Play search row."""

    place_id: str
    name: str
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal: str | None = None
    phone: str | None = None
    website: str | None = None
    indoor_courts: int | None = None
    outdoor_courts: int | None = None
    lat: float | None = None
    lng: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def _headers() -> dict[str, str]:
    return {"User-Agent": USER_AGENT}


def search_url(query: str) -> str:
    return f"{BASE_URL}/search?q={quote_plus(query)}"


def place_url(place_id: str) -> str:
    return f"{BASE_URL}/place?id={place_id}"


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    s = re.sub(r"\s+", " ", text).strip()
    return s or None


def _parse_address_cell(cell: Any) -> tuple[str | None, str | None, str | None, str | None]:
    """(street, city, state, postal) from the Address ``<td>``.

    Shape: ``<a href="/map?id=N">STREET</a> <a href="/city/..">CITY, STATE</a> ZIP``.
    """
    street = city = state = postal = None
    map_link = cell.find("a", href=re.compile(r"^/map\?id="))
    if map_link:
        street = _clean(map_link.get_text(" ", strip=True))
    city_link = cell.find("a", href=re.compile(r"^/city/"))
    if city_link:
        city_state = _clean(city_link.get_text(" ", strip=True))
        if city_state and "," in city_state:
            city, state = (p.strip() for p in city_state.rsplit(",", 1))
        else:
            city = city_state
    zip_match = _ZIP_RE.search(cell.get_text(" ", strip=True))
    if zip_match:
        postal = zip_match.group(1)
    return street, city, state, postal


def parse_search_results(html: str) -> list[PickleballPlace]:
    """Parse the ``/search`` results table into court listings (no coordinates).

    Rows without a ``/place?id=`` link (header row, layout rows) are skipped.
    """
    soup = BeautifulSoup(html, "html.parser")
    places: list[PickleballPlace] = []
    seen: set[str] = set()
    for row in soup.find_all("tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 6:
            continue
        place_link = cells[1].find("a", href=_PLACE_ID_RE)
        if not place_link:
            continue
        pid_match = _PLACE_ID_RE.search(place_link.get("href", ""))
        if not pid_match:
            continue
        place_id = pid_match.group(1)
        if place_id in seen:
            continue
        seen.add(place_id)
        name = _clean(place_link.get_text(" ", strip=True))
        if not name:
            continue

        website = None
        for a in cells[1].find_all("a", href=True):
            if a.get_text(" ", strip=True).lower() == "website":
                href = (a.get("href") or "").strip()
                if href and not href.startswith(("#", "javascript:")):
                    website = href
                break

        street, city, state, postal = _parse_address_cell(cells[2])

        indoor = outdoor = None
        courts_match = _COURTS_RE.search(cells[4].get_text(" ", strip=True))
        if courts_match:
            indoor, outdoor = int(courts_match.group(1)), int(courts_match.group(2))

        phone = None
        tel = cells[5].find("a", href=re.compile(r"^tel:"))
        if tel:
            phone = _clean(tel.get_text(" ", strip=True))

        places.append(
            PickleballPlace(
                place_id=place_id,
                name=name[:300],
                street=street,
                city=city,
                state=state,
                postal=postal,
                phone=phone,
                website=website,
                indoor_courts=indoor,
                outdoor_courts=outdoor,
            )
        )
    return places


def parse_place_latlng(html: str) -> tuple[float | None, float | None]:
    """(lat, lng) from a ``/place`` detail page's Open Graph location meta."""
    lat_m = _LAT_RE.search(html)
    lng_m = _LNG_RE.search(html)
    lat = float(lat_m.group(1)) if lat_m else None
    lng = float(lng_m.group(1)) if lng_m else None
    return lat, lng


def format_address(place: PickleballPlace) -> str | None:
    """Human-readable ``street, city, state zip`` (omitting missing parts).

    WS-4: the street is pre-stripped of any Lake-Havasu-shaped suffix
    (street_line is a no-op for other cities) so the tail never doubles.
    """
    from app.core.address import street_line

    street = street_line(place.street) or place.street
    tail_bits = [b for b in (place.city, place.state) if b]
    tail = ", ".join(tail_bits)
    if place.postal:
        tail = f"{tail} {place.postal}".strip()
    parts = [p for p in (street, tail) if p]
    return ", ".join(parts) or None


def _description(place: PickleballPlace) -> str | None:
    indoor = place.indoor_courts or 0
    outdoor = place.outdoor_courts or 0
    if indoor == 0 and outdoor == 0:
        return None
    bits = []
    if indoor:
        bits.append(f"{indoor} indoor")
    if outdoor:
        bits.append(f"{outdoor} outdoor")
    return "Pickleball courts: " + ", ".join(bits) + "."


def fetch_search(query: str, *, client: httpx.Client | None = None) -> list[PickleballPlace]:
    """Fetch + parse the search results for ``query``. ``client`` is injectable."""
    if client is None:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT, headers=_headers(), follow_redirects=True
        ) as c:
            return fetch_search(query, client=c)
    resp = client.get(search_url(query))
    resp.raise_for_status()
    return parse_search_results(resp.text)


def enrich_latlng(place: PickleballPlace, *, client: httpx.Client | None = None) -> PickleballPlace:
    """Fill ``place.lat``/``lng`` from its detail page (mutates + returns place)."""
    if client is None:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT, headers=_headers(), follow_redirects=True
        ) as c:
            return enrich_latlng(place, client=c)
    resp = client.get(place_url(place.place_id))
    resp.raise_for_status()
    place.lat, place.lng = parse_place_latlng(resp.text)
    return place


def place_to_entity_payload(
    place: PickleballPlace,
    *,
    category_slug: str = DEFAULT_CATEGORY_SLUG,
) -> EntityPayload:
    """Map a :class:`PickleballPlace` to a source-agnostic :class:`EntityPayload`."""
    return EntityPayload(
        name=place.name,
        entity_type="place",
        lat=place.lat,
        lng=place.lng,
        address=format_address(place),
        phone=place.phone,
        website=place.website,
        description=_description(place),
        category_slug=category_slug,
        legacy_category=LEGACY_CATEGORY,
        google_place_id=None,
        source=SOURCE_NAME,
    )
