"""
golakehavasu.com (Visit Lake Havasu / CVB) -- sitemap discovery + event HTML parsing.

Server-rendered Simpleview/IDSS CMS: plain httpx + sitemap, no JS, no proxy.
Fetches and parses; does not write to the database. Mirrors the shape of
``app/contrib/river_scene.py`` so the orchestration / reconciler hand-off
stays identical across event sources.

Parse strategy (verified against live event pages 2026-05-29):
  * Prefer schema.org Event JSON-LD for title / description / image / times.
  * The DOM is AUTHORITATIVE for the calendar date: recurring events
    (e.g. the weekly farmers market) carry a STALE JSON-LD ``startDate``
    while the rendered header shows the correct next occurrence.
  * JSON-LD ``location.address`` is just the event name -- the real venue
    name + street + city/zip live only in the DOM "Location" block.
  * Lat/lon is embedded in the Google static-map ``markers=color:...%7C<lat>,<lng>``.
"""

from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from datetime import time as time_type
from typing import Any

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

from app.db.contribution_store import normalize_submission_url
from app.schemas.contribution import ContributionCreate

SITEMAP_INDEX_URL = "https://www.golakehavasu.com/sitemap.xml"
# The event child sitemap loc contains this substring (e.g.
# ``sitemaps-1-event-default-1-sitemap.xml``).
EVENTS_SITEMAP_SUBSTR = "event-default"
USER_AGENT = "Hava/0.1 (+https://github.com/casey451/havasu-chat)"

SITEMAP_HTTP_TIMEOUT = httpx.Timeout(45.0, connect=20.0)
EVENT_PAGE_HTTP_TIMEOUT = httpx.Timeout(60.0, connect=20.0)
REQUEST_TIMEOUT = EVENT_PAGE_HTTP_TIMEOUT

# Source token (already present in ContributionSource + auto-approve set).
SOURCE_NAME = "go_lake_havasu"

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
# Dash class: hyphen-minus, en dash (U+2013), em dash (U+2014). Kept as an
# ASCII source representation so this file stays ASCII-only.
_DASH = "\\-–—"

_DATE_RE = re.compile(rf"((?:{_MONTHS})\s+\d{{1,2}},\s+\d{{4}})")
_TIME_RE = re.compile(r"(\d{1,2}:\d{2}\s*[AP]M)", re.IGNORECASE)
_LATLON_RE = re.compile(r"markers=color:[^\"'&]*?%7C(-?\d+\.\d+),(-?\d+\.\d+)")
_ZIP_LINE_RE = re.compile(r",\s*AZ\s+\d{5}")
_PHONE_RE = re.compile(r"\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}")


@dataclass
class GoLakeHavasuEvent:
    """Normalized event parsed from a golakehavasu.com event detail page."""

    title: str
    url: str
    start_date: date
    end_date: date
    start_time: time_type
    end_time: time_type | None
    description: str
    venue_name: str | None
    venue_address: str | None
    lat: float | None
    lng: float | None
    image_url: str | None
    organizer_url: str | None
    raw: dict[str, Any] = field(default_factory=dict)


def _headers() -> dict[str, str]:
    return {"User-Agent": USER_AGENT}


def _sleep_polite() -> None:
    time.sleep(1.0)


def _http_get_text(
    url: str,
    client: httpx.Client,
    *,
    timeout: httpx.Timeout | float,
) -> str:
    """GET ``url`` as text with retry on timeout / 5xx, then a polite pause."""

    r: httpx.Response | None = None
    for attempt in range(3):
        try:
            r = client.get(url, timeout=timeout)
            r.raise_for_status()
            break
        except (httpx.TimeoutException, httpx.ReadTimeout, httpx.ConnectTimeout):
            if attempt >= 2:
                raise
            time.sleep(0.5 + 0.5 * attempt)
        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code >= 500 and attempt < 2:
                time.sleep(0.5)
                continue
            raise
    assert r is not None
    text = r.text
    _sleep_polite()
    return text


def fetch_sitemap_urls(*, client: httpx.Client | None = None) -> list[str]:
    """
    Load the sitemap index, follow the ``event-default`` child sitemap, and
    return every event ``<url><loc>`` (no filtering).
    """
    if client is None:
        with httpx.Client(
            timeout=SITEMAP_HTTP_TIMEOUT,
            headers=_headers(),
            follow_redirects=True,
        ) as c:
            return fetch_sitemap_urls(client=c)

    xml_index = _http_get_text(SITEMAP_INDEX_URL, client, timeout=SITEMAP_HTTP_TIMEOUT)
    root = ET.fromstring(xml_index)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    sub_locs: list[str] = []
    for sm in root.findall("sm:sitemap", ns):
        loc = sm.find("sm:loc", ns)
        if loc is not None and loc.text and EVENTS_SITEMAP_SUBSTR in loc.text:
            sub_locs.append(loc.text.strip())

    urls: list[str] = []
    seen_sub: set[str] = set()
    for sub in sub_locs:
        if sub in seen_sub:
            continue
        seen_sub.add(sub)
        xml_page = _http_get_text(sub, client, timeout=SITEMAP_HTTP_TIMEOUT)
        subroot = ET.fromstring(xml_page)
        for url_el in subroot.findall("sm:url", ns):
            loc = url_el.find("sm:loc", ns)
            if loc is not None and loc.text:
                urls.append(loc.text.strip())
    return urls


def _extract_event_jsonld(soup: BeautifulSoup) -> dict[str, Any]:
    """Return the first schema.org ``Event`` object from any ld+json block."""
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        body = script.string or script.get_text() or ""
        if not body.strip():
            continue
        try:
            data = json.loads(body)
        except (ValueError, TypeError):
            continue
        nodes: list[Any] = []
        if isinstance(data, dict):
            if "@graph" in data and isinstance(data["@graph"], list):
                nodes.extend(data["@graph"])
            else:
                nodes.append(data)
        elif isinstance(data, list):
            nodes.extend(data)
        for node in nodes:
            if isinstance(node, dict):
                t = node.get("@type")
                if t == "Event" or (isinstance(t, list) and "Event" in t):
                    return node
    return {}


def _parse_iso_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return dateutil_parser.isoparse(value)
    except (ValueError, TypeError, OverflowError):
        try:
            return dateutil_parser.parse(value)
        except (ValueError, TypeError, OverflowError):
            return None


def _parse_us_date(text: str) -> date | None:
    s = (text or "").strip()
    if not s:
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return dateutil_parser.parse(s, fuzzy=False).date()
    except (ValueError, TypeError, OverflowError):
        return None


def _parse_clock(text: str) -> time_type | None:
    s = (text or "").strip()
    if not s:
        return None
    try:
        return dateutil_parser.parse(f"Jan 1, 2000 {s}").time()
    except (ValueError, TypeError, OverflowError):
        return None


def _header_text_with_date(soup: BeautifulSoup) -> str:
    """Collapsed text of the nearest ancestor of <h1> that contains a date."""
    h1 = soup.find("h1")
    node: Any = h1
    for _ in range(6):
        if node is None:
            break
        collapsed = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
        if _DATE_RE.search(collapsed):
            return collapsed
        node = node.parent
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def _parse_dom_dates_times(
    soup: BeautifulSoup,
) -> tuple[date | None, date | None, time_type | None, time_type | None]:
    header = _header_text_with_date(soup)
    dates = _DATE_RE.findall(header)
    times = _TIME_RE.findall(header)
    start_d = _parse_us_date(dates[0]) if dates else None
    end_d = _parse_us_date(dates[1]) if len(dates) >= 2 else None
    start_t = _parse_clock(times[0]) if times else None
    end_t = _parse_clock(times[1]) if len(times) >= 2 else None
    return start_d, end_d, start_t, end_t


def _title_from_soup(soup: BeautifulSoup, jsonld: dict[str, Any]) -> str:
    name = jsonld.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()[:500]
    h1 = soup.find("h1")
    if h1:
        txt = h1.get_text(" ", strip=True)
        if txt:
            return txt[:500]
    return "Untitled event"


def _venue_from_soup(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    """Parse the DOM "Location" block -> (venue_name, full_address).

    Block shape (verified): ['Location', <venue>, <street>, '<city>, AZ <zip>', '<phone?>'].
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
    lines = [ln for ln in lines if ln and ln.lower() != "location"]
    city_idx = next((i for i, ln in enumerate(lines) if _ZIP_LINE_RE.search(ln)), None)
    if city_idx is None:
        return None, None
    city_line = lines[city_idx]
    street = lines[city_idx - 1] if city_idx - 1 >= 0 else None
    venue = lines[city_idx - 2] if city_idx - 2 >= 0 else None
    # Guard: if "street" is actually the venue (no second line), don't duplicate.
    if street and _PHONE_RE.fullmatch(street):
        street = None
    parts = [p for p in (street, city_line) if p]
    address = ", ".join(parts) if parts else None
    return (venue or street), address


def _latlon_from_html(html: str) -> tuple[float | None, float | None]:
    m = _LATLON_RE.search(html)
    if not m:
        return None, None
    try:
        return float(m.group(1)), float(m.group(2))
    except (TypeError, ValueError):
        return None, None


def _image_from(soup: BeautifulSoup, jsonld: dict[str, Any]) -> str | None:
    og = soup.find("meta", attrs={"property": "og:image"})
    if og and og.get("content"):
        return str(og["content"]).strip()
    img = jsonld.get("image")
    if isinstance(img, dict) and img.get("url"):
        return str(img["url"]).strip()
    if isinstance(img, str) and img.strip():
        return img.strip()
    return None


def _organizer_url_from(soup: BeautifulSoup) -> str | None:
    for a in soup.find_all("a", href=True):
        label = a.get_text(" ", strip=True).lower()
        if "go to website" in label or label == "website":
            href = (a.get("href") or "").strip()
            if href and not href.startswith(("#", "javascript:")):
                return href
    return None


def _description_from(soup: BeautifulSoup, jsonld: dict[str, Any]) -> str:
    candidates: list[str] = []
    ld_desc = jsonld.get("description")
    if isinstance(ld_desc, str) and ld_desc.strip():
        candidates.append(ld_desc.strip())
    # Try a DOM "Overview" section for a fuller blurb.
    heading = soup.find(
        lambda tag: (
            tag.name in ("h2", "h3", "h4") and tag.get_text(strip=True).lower() == "overview"
        )
    )
    if heading:
        chunks: list[str] = []
        for sib in heading.find_all_next(["p", "li"], limit=12):
            t = sib.get_text(" ", strip=True)
            if t:
                chunks.append(t)
        if chunks:
            candidates.append("\n\n".join(chunks))
    if not candidates:
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            candidates.append(str(meta["content"]).strip())
    return max(candidates, key=len) if candidates else ""


def fetch_and_parse_event(
    url: str,
    *,
    client: httpx.Client | None = None,
    today: date | None = None,
) -> GoLakeHavasuEvent | None:
    """Fetch one event page and parse it.

    Returns ``None`` if undatable or the start date is in the past.
    """
    if client is None:
        with httpx.Client(
            timeout=EVENT_PAGE_HTTP_TIMEOUT,
            headers=_headers(),
            follow_redirects=True,
        ) as c:
            return fetch_and_parse_event(url, client=c, today=today)

    as_of = today if today is not None else date.today()
    html = _http_get_text(url, client, timeout=EVENT_PAGE_HTTP_TIMEOUT)
    soup = BeautifulSoup(html, "html.parser")
    jsonld = _extract_event_jsonld(soup)

    dom_start, dom_end, dom_st, dom_et = _parse_dom_dates_times(soup)

    ld_start = _parse_iso_dt(jsonld.get("startDate"))
    ld_end = _parse_iso_dt(jsonld.get("endDate"))

    # DOM date is authoritative (recurring JSON-LD dates go stale); JSON-LD is
    # the fallback when the DOM header has no parsable date.
    start_d = dom_start or (ld_start.date() if ld_start else None)
    if start_d is None:
        return None
    if start_d < as_of:
        return None

    end_d = dom_end
    if end_d is None and ld_end is not None and ld_start is not None:
        if ld_end.date() > ld_start.date() and dom_start is None:
            end_d = ld_end.date()
    if end_d is None or end_d < start_d:
        end_d = start_d

    start_t = dom_st or (ld_start.timetz().replace(tzinfo=None) if ld_start else None)
    if start_t is None:
        start_t = time_type(12, 0, 0)
    end_t = dom_et or (ld_end.timetz().replace(tzinfo=None) if ld_end else None)
    if end_t is not None and end_t == start_t:
        end_t = None

    title = _title_from_soup(soup, jsonld)
    venue_name, venue_address = _venue_from_soup(soup)
    lat, lng = _latlon_from_html(html)
    image_url = _image_from(soup, jsonld)
    organizer_url = _organizer_url_from(soup)
    description = _description_from(soup, jsonld)

    return GoLakeHavasuEvent(
        title=title,
        url=url.strip(),
        start_date=start_d,
        end_date=end_d,
        start_time=start_t,
        end_time=end_t,
        description=description,
        venue_name=venue_name,
        venue_address=venue_address,
        lat=lat,
        lng=lng,
        image_url=image_url,
        organizer_url=organizer_url,
        raw={"jsonld_present": bool(jsonld)},
    )


def _format_date_heading(start_d: date, end_d: date) -> str:
    if end_d == start_d:
        return f"Date: {start_d.strftime('%B %d, %Y')}"
    if start_d.year == end_d.year and start_d.month == end_d.month:
        return f"Date: {start_d.strftime('%B')} {start_d.day}-{end_d.day}, {start_d.year}"
    return f"Date: {start_d.strftime('%B %d, %Y')}-{end_d.strftime('%B %d, %Y')}"


def _public_url(ev: GoLakeHavasuEvent) -> str:
    """Click-through URL: organizer 'Go To Website', else the event page."""
    if ev.organizer_url:
        cand = ev.organizer_url.strip()
        if not cand.startswith(("http://", "https://")):
            cand = f"https://{cand.lstrip('/')}"
        return cand
    return ev.url


def normalize_to_contribution(ev: GoLakeHavasuEvent) -> ContributionCreate:
    """Map a :class:`GoLakeHavasuEvent` to :class:`ContributionCreate`.

    ``source_url`` is the canonical golakehavasu event page (per-source dedupe
    key); ``submission_url`` is the public organizer link when present.
    """
    date_line = _format_date_heading(ev.start_date, ev.end_date)
    if ev.end_time is not None:
        time_line = f"Time: {ev.start_time.strftime('%H:%M')} - {ev.end_time.strftime('%H:%M')}"
    else:
        time_line = f"Time: {ev.start_time.strftime('%H:%M')}"

    lines: list[str] = [date_line, time_line, "", (ev.description or "").strip(), ""]
    if ev.venue_name:
        lines.append(f"Venue: {ev.venue_name}")
    if ev.venue_address:
        lines.append(f"Address: {ev.venue_address}")
    if ev.lat is not None and ev.lng is not None:
        lines.append(f"Coordinates: {ev.lat},{ev.lng}")
    if ev.image_url:
        lines.append(f"Image: {ev.image_url}")

    notes = "\n".join(lines).strip()
    if len(notes) < 20:
        notes = f"{notes}\nEvent page: {ev.url}".strip()

    return ContributionCreate(
        entity_type="event",
        submission_name=ev.title[:200],
        submission_url=_public_url(ev),  # type: ignore[arg-type]
        source_url=normalize_submission_url(ev.url),
        submission_notes=notes,
        event_date=ev.start_date,
        event_end_date=(ev.end_date if ev.end_date > ev.start_date else None),
        event_time_start=ev.start_time,
        event_time_end=ev.end_time,
        source=SOURCE_NAME,
        unverified=False,
    )
