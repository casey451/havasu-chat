"""PDGA disc-golf course-directory scrape: fetch + parse + payload map.

Mirrors :mod:`app.contrib.usapickleball`: pure parse helpers run on fetched HTML
strings (unit-tested against fixtures, no network) and a thin injectable-client
fetch layer wraps them. The loader (:mod:`scripts.pdga_load`) owns persistence.

**Data source.** ``pdga.com/course-directory`` is the Professional Disc Golf
Association's official directory. Its official REST API (``api.pdga.com``) is
gated behind a Developer Program that is closed to new applicants, so we read
the public page instead. The page embeds a Leaflet map whose ``features`` JSON
lists EVERY course (``name``, ``lat``, ``lon``, course slug) regardless of the
table's exposed filters -- so we parse the full blob and filter client-side by
proximity to a center point (Lake Havasu City by default). Per-course address +
hole count + course type live on the ``/course-directory/course/<slug>`` detail
page, fetched as an enrichment step.

``phone`` is not published in the directory and ``website`` is set to the
canonical PDGA course page. Records map to ``source="pdga"`` under the new
``disc-golf`` subcategory; the loader resolves the Tier-1
``classes-sports-recreation`` slug to ``Provider.category_id``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from math import asin, cos, radians, sin, sqrt
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.contrib.ingest_base import EntityPayload

BASE_URL = "https://www.pdga.com"
COURSE_DIRECTORY_URL = f"{BASE_URL}/course-directory"
USER_AGENT = "Hava/0.1 (+https://github.com/casey451/havasu-chat)"
REQUEST_TIMEOUT = httpx.Timeout(60.0, connect=20.0)

SOURCE_NAME = "pdga"
DEFAULT_CATEGORY_SLUG = "classes-sports-recreation"
SUBCATEGORY = "disc-golf"
LEGACY_CATEGORY = "disc_golf"

# Lake Havasu City anchor + default scope radius. The directory blob is national,
# so a loader run must restrict to its service area; tune via --radius-km.
LHC_LAT = 34.4839
LHC_LNG = -114.3225
DEFAULT_RADIUS_KM = 80.0

_COURSE_SLUG_RE = re.compile(r"/course-directory/course/([a-z0-9-]+)")
_INT_RE = re.compile(r"\d+")


@dataclass
class DiscGolfCourse:
    """One disc-golf course parsed from the PDGA directory + detail page."""

    slug: str
    name: str
    lat: float | None = None
    lng: float | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal: str | None = None
    holes: int | None = None
    course_type: str | None = None
    year_established: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def _headers() -> dict[str, str]:
    return {"User-Agent": USER_AGENT}


def course_url(slug: str) -> str:
    return f"{COURSE_DIRECTORY_URL}/course/{slug}"


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * r * asin(min(1.0, sqrt(a)))


def _extract_features_array(html: str) -> list[dict[str, Any]]:
    """Pull the Leaflet ``"features":[...]`` JSON array out of the page.

    Brackets are balanced from the first ``[`` after the ``"features":`` key so a
    popup string containing brackets does not truncate the array.
    """
    key = html.find('"features":')
    if key == -1:
        return []
    start = html.find("[", key)
    if start == -1:
        return []
    depth = 0
    for i in range(start, len(html)):
        ch = html[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start : i + 1])
                except json.JSONDecodeError:
                    return []
    return []


def parse_courses(html: str) -> list[DiscGolfCourse]:
    """Parse the directory page's map blob into courses (name/lat/lng/slug only).

    Features without a valid course slug or coordinates are skipped.
    """
    courses: list[DiscGolfCourse] = []
    seen: set[str] = set()
    for feat in _extract_features_array(html):
        popup = feat.get("popup") or ""
        slug_m = _COURSE_SLUG_RE.search(popup)
        if not slug_m:
            continue
        slug = slug_m.group(1)
        if slug in seen:
            continue
        name = re.sub(r"<[^>]+>", "", popup).strip()
        if not name:
            continue
        try:
            lat = float(feat["lat"])
            lng = float(feat["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        seen.add(slug)
        courses.append(DiscGolfCourse(slug=slug, name=name[:300], lat=lat, lng=lng))
    return courses


def filter_near(
    courses: list[DiscGolfCourse],
    *,
    center_lat: float = LHC_LAT,
    center_lng: float = LHC_LNG,
    radius_km: float = DEFAULT_RADIUS_KM,
) -> list[DiscGolfCourse]:
    """Keep courses within ``radius_km`` of the center, nearest first."""
    scored: list[tuple[float, DiscGolfCourse]] = []
    for c in courses:
        if c.lat is None or c.lng is None:
            continue
        d = haversine_km(center_lat, center_lng, c.lat, c.lng)
        if d <= radius_km:
            scored.append((d, c))
    scored.sort(key=lambda t: t[0])
    return [c for _, c in scored]


def _labeled_field(soup: BeautifulSoup, label: str) -> str | None:
    """Value of a Drupal ``field-label``/``field-item`` pair, by label text."""
    for lab in soup.find_all("div", class_="field-label"):
        if lab.get_text(" ", strip=True).rstrip(":").strip().lower() == label.lower():
            wrapper = lab.parent
            item = wrapper.find("div", class_="field-item") if wrapper else None
            if item:
                text = item.get_text(" ", strip=True)
                return text or None
    return None


def parse_course_detail(html: str) -> dict[str, Any]:
    """(street, city, state, postal, holes, course_type, year_established) from a
    course detail page. Missing fields are ``None``."""
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, Any] = {
        "street": None,
        "city": None,
        "state": None,
        "postal": None,
        "holes": None,
        "course_type": None,
        "year_established": None,
    }
    thoroughfare = soup.find("div", class_="thoroughfare")
    if thoroughfare:
        out["street"] = thoroughfare.get_text(" ", strip=True) or None
    for key, cls in (("city", "locality"), ("state", "state"), ("postal", "postal-code")):
        node = soup.find("span", class_=cls)
        if node:
            out[key] = node.get_text(" ", strip=True) or None

    holes = _labeled_field(soup, "# Holes")
    if holes:
        m = _INT_RE.search(holes)
        if m:
            out["holes"] = int(m.group(0))
    out["course_type"] = _labeled_field(soup, "Course Type")
    out["year_established"] = _labeled_field(soup, "Year Established")
    return out


def format_address(course: DiscGolfCourse) -> str | None:
    tail_bits = [b for b in (course.city, course.state) if b]
    tail = ", ".join(tail_bits)
    if course.postal:
        tail = f"{tail} {course.postal}".strip()
    parts = [p for p in (course.street, tail) if p]
    return ", ".join(parts) or None


def _description(course: DiscGolfCourse) -> str | None:
    bits: list[str] = []
    if course.holes:
        bits.append(f"{course.holes}-hole disc golf course")
    elif course.course_type:
        bits.append("Disc golf course")
    if course.course_type:
        bits.append(course.course_type)
    return (". ".join(bits) + ".") if bits else None


def fetch_courses(*, client: httpx.Client | None = None) -> list[DiscGolfCourse]:
    """Fetch the directory page and parse its full course list. Injectable client."""
    if client is None:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT, headers=_headers(), follow_redirects=True
        ) as c:
            return fetch_courses(client=c)
    resp = client.get(COURSE_DIRECTORY_URL)
    resp.raise_for_status()
    return parse_courses(resp.text)


def enrich_course(course: DiscGolfCourse, *, client: httpx.Client | None = None) -> DiscGolfCourse:
    """Fill address + holes + course type from the detail page (mutates + returns)."""
    if client is None:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT, headers=_headers(), follow_redirects=True
        ) as c:
            return enrich_course(course, client=c)
    resp = client.get(course_url(course.slug))
    resp.raise_for_status()
    detail = parse_course_detail(resp.text)
    course.street = detail["street"]
    course.city = detail["city"]
    course.state = detail["state"]
    course.postal = detail["postal"]
    course.holes = detail["holes"]
    course.course_type = detail["course_type"]
    course.year_established = detail["year_established"]
    return course


def course_to_entity_payload(
    course: DiscGolfCourse,
    *,
    category_slug: str = DEFAULT_CATEGORY_SLUG,
) -> EntityPayload:
    """Map a :class:`DiscGolfCourse` to a source-agnostic :class:`EntityPayload`.

    ``website`` is the canonical PDGA course page (the directory does not publish
    a course's own site); ``phone`` is unavailable from this source.
    """
    return EntityPayload(
        name=course.name,
        entity_type="place",
        lat=course.lat,
        lng=course.lng,
        address=format_address(course),
        phone=None,
        website=course_url(course.slug),
        description=_description(course),
        category_slug=category_slug,
        legacy_category=LEGACY_CATEGORY,
        google_place_id=None,
        source=SOURCE_NAME,
    )
