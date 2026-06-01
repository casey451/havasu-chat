"""
RiverScene Magazine — sitemap discovery + event HTML parsing (Phase 8.10).

Fetches and parses; does not write to the database.
"""

from __future__ import annotations

import logging
import os
import random
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from datetime import time as time_type
from typing import Any

import httpx
from bs4 import BeautifulSoup, NavigableString, Tag
from dateutil import parser as dateutil_parser

from app.db.contribution_store import normalize_submission_url
from app.schemas.contribution import ContributionCreate

logger = logging.getLogger(__name__)

SITEMAP_INDEX_URL = "https://riverscenemagazine.com/wp-sitemap.xml"
EVENTS_SITEMAP_PREFIX = "wp-sitemap-posts-events-"
USER_AGENT = "Hava/0.1 (+https://github.com/casey451/havasu-chat)"
RIVER_SCENE_PROXY_ENV = "RIVER_SCENE_SCRAPE_PROXY_URL"
_FALLBACK_PROXY_ENV = "GAS_SCRAPE_PROXY_URL"

# Sitemaps are small XML; event pages can be slow (WordPress + assets).
SITEMAP_HTTP_TIMEOUT = httpx.Timeout(20.0, connect=8.0)
EVENT_PAGE_HTTP_TIMEOUT = httpx.Timeout(45.0, connect=12.0)

# Default ``httpx.Client`` ceiling for :func:`run_pull` (matches event pages).
REQUEST_TIMEOUT = EVENT_PAGE_HTTP_TIMEOUT

# Labels consumed by ``fetch_and_parse_event`` / ``normalize_to_contribution`` pass-2 rescue.
# Keep aligned with ``labels.get(...)`` reads — add entries only when a consumer exists.
RIVER_SCENE_DETAIL_LABELS: frozenset[str] = frozenset(
    {
        "End Date",
        "Event Category",
        "Facebook",
        "Organizer",
        "Start Date",
        "Time",
        "Venue",
        "Website",
    }
)


@dataclass
class RiverSceneEvent:
    """Normalized event parsed from a RiverScene event detail HTML page."""

    title: str
    url: str
    start_date: date
    end_date: date
    start_time: time_type
    end_time: time_type
    description_html: str
    venue_name: str | None
    venue_address: str | None
    organizer: str | None
    category_slugs: list[str]
    raw: dict[str, Any] = field(default_factory=dict)


def _headers() -> dict[str, str]:
    return {"User-Agent": USER_AGENT}


def _sleep_polite() -> None:
    time.sleep(0.25)


def _proxy_url() -> str | None:
    specific = (os.getenv(RIVER_SCENE_PROXY_ENV) or "").strip()
    if specific:
        return specific
    fallback = (os.getenv(_FALLBACK_PROXY_ENV) or "").strip()
    return fallback or None


def build_river_scene_client(*, timeout: httpx.Timeout) -> httpx.Client:
    kwargs: dict[str, Any] = {
        "timeout": timeout,
        "headers": _headers(),
        "follow_redirects": True,
    }
    proxy = _proxy_url()
    if proxy:
        try:
            return httpx.Client(proxy=proxy, **kwargs)
        except TypeError:
            return httpx.Client(proxies=proxy, **kwargs)
    return httpx.Client(**kwargs)


def _http_get_text(
    url: str,
    client: httpx.Client,
    *,
    timeout: httpx.Timeout | float,
) -> str:
    """
    GET ``url`` as text.

    Retries on connect/read timeout (up to 3 attempts) and once more on 5xx;
    then a polite pause after a successful response.
    """

    def once() -> httpx.Response:
        return client.get(url, timeout=timeout)

    r: httpx.Response | None = None
    max_attempts = 4
    retryable_statuses = {408, 425, 429, 500, 502, 503, 504}
    for attempt in range(max_attempts):
        try:
            r = once()
            r.raise_for_status()
            break
        except (
            httpx.TimeoutException,
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.ConnectError,
            httpx.ReadError,
            httpx.RemoteProtocolError,
        ):
            if attempt >= max_attempts - 1:
                raise
            time.sleep(0.35 * (2**attempt) + random.uniform(0.0, 0.25))
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response is not None else None
            if status_code in retryable_statuses and attempt < max_attempts - 1:
                time.sleep(0.35 * (2**attempt) + random.uniform(0.0, 0.25))
                continue
            raise
        except httpx.RequestError:
            if attempt >= max_attempts - 1:
                raise
            time.sleep(0.35 * (2**attempt) + random.uniform(0.0, 0.25))
    assert r is not None
    if attempt > 0:
        logger.info("river_scene_http.retry_success url=%s attempts=%d", url, attempt + 1)
    text = r.text
    _sleep_polite()
    return text


def _parse_us_date(cell_text: str) -> date | None:
    s = (cell_text or "").strip()
    if not s:
        return None
    try:
        return dateutil_parser.parse(s, fuzzy=False).date()
    except (ValueError, TypeError, OverflowError):
        pass
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_time_cell(cell_text: str) -> time_type | None:
    s = (cell_text or "").strip()
    if not s:
        return None
    try:
        return dateutil_parser.parse(f"Jan 1, 2000 {s}").time()
    except (ValueError, TypeError, OverflowError):
        return None


def _strip_html_to_text(html: str) -> str:
    if not html or not str(html).strip():
        return ""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def _format_date_heading(start_d: date, end_d: date) -> str:
    if end_d == start_d:
        return f"Date: {start_d.strftime('%B %d, %Y')}"
    if start_d.year == end_d.year and start_d.month == end_d.month:
        return f"Date: {start_d.strftime('%B')} {start_d.day}–{end_d.day}, {start_d.year}"
    return f"Date: {start_d.strftime('%B %d, %Y')}–{end_d.strftime('%B %d, %Y')}"


def _title_from_soup(soup: BeautifulSoup) -> str:
    t = soup.find("title")
    if t and t.string:
        s = " ".join(t.string.split())
        if s.endswith(" | RiverScene Magazine"):
            s = s[: -len(" | RiverScene Magazine")].strip()
        if s.startswith("RiverScene Magazine | "):
            s = s[len("RiverScene Magazine | ") :].strip()
        if s:
            return s[:500]
    for h2 in soup.find_all("h2"):
        cls = h2.get("class")
        cl = " ".join(cls) if isinstance(cls, list) else (cls or "")
        cl_l = cl.lower()
        if "event" in cl_l or "title" in cl_l:
            txt = h2.get_text(" ", strip=True)
            if txt:
                return txt[:500]
    return "Untitled event"


def _has_entry_content_class(classes: Any) -> bool:
    if not classes:
        return False
    if isinstance(classes, str):
        tokens = classes.split()
    else:
        tokens = list(classes)
    return "entry-content" in tokens


def _find_event_details_table(soup: BeautifulSoup) -> Tag | None:
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 2 and tds[0].get_text(strip=True) == "Start Date":
                return table
    return None


def _detail_link_or_plain(label: str, value_cell: Tag) -> str:
    """Prefer ``<a href>`` for Website and Facebook cells; else visible text."""
    if label in ("Website", "Facebook"):
        a = value_cell.find("a", href=True)
        link = (a.get("href") or "").strip() if a else ""
        return link or value_cell.get_text(" ", strip=True)
    return value_cell.get_text(" ", strip=True)


def _normalize_scheme_optional_https(candidate: str) -> str:
    s = candidate.strip()
    if not s:
        return s
    if not s.startswith(("http://", "https://")):
        return f"https://{s.lstrip('/')}"
    return s


def _table_label_map(table: Tag) -> dict[str, str]:
    """Extract Info/Details label pairs; pass 2 rescues orphan ``<td>`` pairs (no ``<tr>`` wrap)."""
    out: dict[str, str] = {}
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        label = tds[0].get_text(strip=True)
        value_cell = tds[1]
        if label in ("Website", "Facebook"):
            out[label] = _detail_link_or_plain(label, value_cell)
        else:
            out[label] = value_cell.get_text(" ", strip=True)

    tds_all = table.find_all("td")
    for i in range(len(tds_all) - 1):
        lab = tds_all[i].get_text(strip=True)
        if lab not in RIVER_SCENE_DETAIL_LABELS or lab in out:
            continue
        value_cell = tds_all[i + 1]
        if lab in ("Website", "Facebook"):
            out[lab] = _detail_link_or_plain(lab, value_cell)
        else:
            out[lab] = value_cell.get_text(" ", strip=True)
    return out


def _description_above_table(soup: BeautifulSoup, table: Tag) -> str:
    ec = soup.find("div", class_=_has_entry_content_class)
    if not ec or not isinstance(ec, Tag):
        return ""
    parts: list[str] = []
    for sib in table.previous_siblings:
        if isinstance(sib, NavigableString):
            continue
        if isinstance(sib, Tag):
            parts.append(str(sib))
    html_frag = "".join(parts)
    if not html_frag.strip():
        return ""
    inner = BeautifulSoup(html_frag, "html.parser")
    chunks: list[str] = []
    for el in inner.find_all(["p", "li", "div"]):
        t = el.get_text(" ", strip=True)
        if t:
            chunks.append(t)
    if chunks:
        return "\n\n".join(chunks)
    return _strip_html_to_text(html_frag)


def _clean_venue_text(s: str) -> str:
    t = (s or "").strip()
    t = re.sub(r"\s*No Address Available\s*$", "", t, flags=re.I).strip()
    return t


def fetch_sitemap_urls(
    *, client: httpx.Client | None = None, start_date: date | None = None
) -> list[str]:
    """
    Load ``wp-sitemap.xml``, follow ``wp-sitemap-posts-events-*.xml`` children,
    and return every ``<url><loc>``.

    When ``start_date`` is provided, entries with a parseable ``<lastmod>`` that
    predate ``start_date`` are skipped to avoid fetching thousands of stale pages.
    """
    if client is None:
        with build_river_scene_client(timeout=SITEMAP_HTTP_TIMEOUT) as c:
            return fetch_sitemap_urls(client=c, start_date=start_date)

    xml_index = _http_get_text(SITEMAP_INDEX_URL, client, timeout=SITEMAP_HTTP_TIMEOUT)
    root = ET.fromstring(xml_index)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    sub_locs: list[str] = []
    for sm in root.findall("sm:sitemap", ns):
        loc = sm.find("sm:loc", ns)
        if loc is not None and loc.text and EVENTS_SITEMAP_PREFIX in loc.text:
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
            if loc is None or not loc.text:
                continue
            if start_date is not None:
                lastmod = url_el.find("sm:lastmod", ns)
                if lastmod is not None and lastmod.text:
                    try:
                        parsed_lastmod = dateutil_parser.parse(lastmod.text).date()
                    except (ValueError, TypeError, OverflowError):
                        parsed_lastmod = None
                    if parsed_lastmod is not None and parsed_lastmod < start_date:
                        continue
            urls.append(loc.text.strip())
    return urls


def fetch_and_parse_event(
    url: str,
    *,
    client: httpx.Client | None = None,
    today: date | None = None,
) -> RiverSceneEvent | None:
    """Fetch one event page and parse it. Returns ``None`` if unparseable or start date is in the past."""
    if client is None:
        with build_river_scene_client(timeout=EVENT_PAGE_HTTP_TIMEOUT) as c:
            return fetch_and_parse_event(url, client=c, today=today)

    as_of = today if today is not None else date.today()
    html = _http_get_text(url, client, timeout=EVENT_PAGE_HTTP_TIMEOUT)
    soup = BeautifulSoup(html, "html.parser")
    table = _find_event_details_table(soup)
    if table is None:
        return None

    labels = _table_label_map(table)
    start_raw = labels.get("Start Date")
    start_d = _parse_us_date(start_raw or "")
    if start_d is None:
        return None
    if start_d < as_of:
        return None

    end_raw = labels.get("End Date")
    end_d = _parse_us_date(end_raw) if end_raw else start_d
    if end_d is None:
        end_d = start_d
    if end_d < start_d:
        end_d = start_d

    time_raw = labels.get("Time")
    st = _parse_time_cell(time_raw or "") if time_raw else None
    if st is None:
        st = time_type(12, 0, 0)
    et = st

    org = (labels.get("Organizer") or "").strip() or None
    venue_txt = _clean_venue_text(labels.get("Venue") or "")
    venue_name = venue_txt or None
    venue_address = None

    cat_cell = labels.get("Event Category")
    cats: list[str] = []
    if cat_cell:
        cats.append(cat_cell.strip())

    title = _title_from_soup(soup)
    desc_html = _description_above_table(soup, table)
    if not desc_html.strip():
        desc_html = ""

    return RiverSceneEvent(
        title=title,
        url=url.strip(),
        start_date=start_d,
        end_date=end_d,
        start_time=st,
        end_time=et,
        description_html=desc_html,
        venue_name=venue_name,
        venue_address=venue_address,
        organizer=org,
        category_slugs=cats,
        raw={"labels": labels},
    )


def _article_url_with_scheme(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return u
    return u if u.startswith(("http://", "https://")) else f"https://{u.lstrip('/')}"


def _submission_public_url(rse: RiverSceneEvent) -> str:
    """Public click-through URL: Website, then Facebook, then the River Scene article URL."""
    labels = rse.raw.get("labels") or {}
    if not isinstance(labels, dict):
        return _article_url_with_scheme(rse.url)
    for key in ("Website", "Facebook"):
        val = labels.get(key)
        if val and isinstance(val, str):
            cand = val.strip()
            if cand:
                return _normalize_scheme_optional_https(cand)
    return _article_url_with_scheme(rse.url)


def normalize_to_contribution(rse: RiverSceneEvent) -> ContributionCreate:
    """
    Map a :class:`RiverSceneEvent` to :class:`ContributionCreate` for the review queue.

    The ``event_date`` / ``event_end_date`` / ``event_time_start`` / ``event_time_end`` fields mirror the source;
    the multi-day range is also spelled out in ``submission_notes`` for operators.
    """
    plain = _strip_html_to_text(rse.description_html)
    # If source page has no body prose, leave description empty rather
    # than fabricating operator-facing scaffolding into a user-facing field.

    date_line = _format_date_heading(rse.start_date, rse.end_date)
    time_line = f"Time: {rse.start_time.strftime('%H:%M')} – {rse.end_time.strftime('%H:%M')}"

    lines: list[str] = [
        date_line,
        time_line,
        "",
        plain,
        "",
    ]
    if rse.venue_name:
        lines.append(f"Venue: {rse.venue_name}")
    if rse.venue_address:
        lines.append(f"Address: {rse.venue_address}")
    if rse.organizer:
        lines.append(f"Organizer: {rse.organizer}")
    if rse.category_slugs:
        lines.append(f"Categories: {', '.join(rse.category_slugs)}")

    notes = "\n".join(lines).strip()

    if len(notes) < 20:
        notes = notes + "\n" + f"Event page: {rse.url}"

    su = _submission_public_url(rse)
    article_key = normalize_submission_url(_article_url_with_scheme(rse.url))
    et_end: time_type | None = rse.end_time
    if rse.end_date == rse.start_date and rse.end_time == rse.start_time:
        et_end = None

    if rse.end_date is None or rse.end_date <= rse.start_date:
        event_end_date: date | None = None
    else:
        event_end_date = rse.end_date

    return ContributionCreate(
        entity_type="event",
        submission_name=rse.title[:200],
        submission_url=su,  # type: ignore[arg-type]
        source_url=article_key,
        submission_notes=notes,
        event_date=rse.start_date,
        event_end_date=event_end_date,
        event_time_start=rse.start_time,
        event_time_end=et_end,
        source="river_scene_import",
        unverified=False,
    )
