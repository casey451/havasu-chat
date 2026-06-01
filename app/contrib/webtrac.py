"""
Parser + fetcher for Lake Havasu City's WebTrac registration system
(Vermont Systems WebTrac 3.1.x).

The system at ``register.lhcaz.gov`` is server-rendered HTML. The activity
search page (``search.html?module=AR``) returns a full document containing
every program in the requested type/category, with each program's sections
embedded inline (date, time, days, location, ages, cost, availability).
Sections are *not* lazy-loaded — one GET yields the full data.

This module owns:
  - :class:`Section` — one schedulable instance under a parent program
  - :func:`parse_search_html` — pure parser over response HTML
  - :func:`fetch_search_html` — live fetcher (handles session bootstrap)

It does *not* yet write to the catalog. The CLI in
``scripts/webtrac_pull.py`` is a thin driver that exercises this module
and emits JSON for downstream review.

Schema notes:
  Programs are the parent grouping (e.g. "Adult art and crafts" — 501057),
  Sections are the actual scheduled occurrences (e.g.
  "Mason jar Terrarium 1-2:30pm" — FMID=63751705). Single-day classes
  appear with start_date == end_date; recurring programs (e.g. After
  School Programs) use a date range plus ``days`` for the weekly pattern.

Availability:
  Each section row carries a CSS class like ``itemstatus--available`` /
  ``itemstatus--unavailable`` / ``itemstatus--waitlist`` etc. The
  ``available_for_signup`` boolean exposes the simple binary used by the
  Hava chat layer to filter out full sections by default.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timezone
from typing import Any, Iterable

import httpx
from bs4 import BeautifulSoup, Tag

# ---------------------------------------------------------------------------
# Data shape
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30.0
BASE_URL = "https://register.lhcaz.gov/webtrac/web"
SEARCH_URL = f"{BASE_URL}/search.html"
SPLASH_URL = f"{BASE_URL}/splash.html"
ITEMINFO_URL = f"{BASE_URL}/iteminfo.html"


@dataclass(frozen=True)
class Section:
    """A single schedulable occurrence under a parent program."""

    fmid: int  # WebTrac's stable section ID
    program_id: int  # Parent program code
    program_name: str  # e.g. "Adult art and crafts"
    section_name: str  # e.g. "Mason jar Terrarium 1-2:30pm"
    availability_state: str  # raw CSS suffix (available, unavailable, ...)
    available_for_signup: bool  # True iff state == "available"
    availability_label: str  # human label as shown on page
    start_date: date | None
    end_date: date | None
    start_time: time | None
    end_time: time | None
    days: tuple[str, ...]  # ("M","Tu","W","Th") etc.
    location: str
    age_min: float | None
    age_max: float | None
    cost_resident: float | None
    cost_nonresident: float | None
    info_url: str  # iteminfo.html?Module=AR&FMID=...
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    # Convenience for JSON-friendly export
    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["start_date"] = self.start_date.isoformat() if self.start_date else None
        out["end_date"] = self.end_date.isoformat() if self.end_date else None
        out["start_time"] = self.start_time.isoformat() if self.start_time else None
        out["end_time"] = self.end_time.isoformat() if self.end_time else None
        out["days"] = list(self.days)
        out.pop("raw", None)
        return out


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_FMID_RE = re.compile(r"FMID=(\d+)", re.IGNORECASE)
_AGE_RE = re.compile(r"([\d.]+)\s*-\s*([\d.]+)")
_COST_RE = re.compile(r"\$?\s*([\d.]+)\s*/\s*\$?\s*([\d.]+)")
_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2,4})")
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(am|pm)", re.IGNORECASE)
_AVAIL_PREFIX = "itemstatus--"


def _text(tag: Tag | None) -> str:
    return tag.get_text(" ", strip=True) if tag else ""


def _parse_date(s: str) -> date | None:
    s = s.strip()
    if not s:
        return None
    m = _DATE_RE.search(s)
    if not m:
        return None
    mo, d, y = m.groups()
    yi = int(y)
    if yi < 100:
        yi += 2000
    try:
        return date(yi, int(mo), int(d))
    except ValueError:
        return None


def _parse_time(s: str) -> time | None:
    s = s.strip()
    if not s:
        return None
    m = _TIME_RE.search(s)
    if not m:
        return None
    h, mn, ap = m.groups()
    h = int(h)
    mn = int(mn)
    if ap.lower() == "pm" and h != 12:
        h += 12
    if ap.lower() == "am" and h == 12:
        h = 0
    try:
        return time(h, mn)
    except ValueError:
        return None


def _parse_dates_cell(td: Tag) -> tuple[date | None, date | None]:
    spans = td.select("span.nowrap")
    if len(spans) >= 2:
        return _parse_date(_text(spans[0])), _parse_date(_text(spans[1]))
    if len(spans) == 1:
        d = _parse_date(_text(spans[0]))
        return d, d
    txt = _text(td)
    parts = [p.strip() for p in txt.split("-") if p.strip()]
    if len(parts) >= 2:
        return _parse_date(parts[0]), _parse_date(parts[1])
    if len(parts) == 1:
        d = _parse_date(parts[0])
        return d, d
    return None, None


def _parse_times_cell(td: Tag) -> tuple[time | None, time | None]:
    spans = td.select("span.nowrap")
    if len(spans) >= 2:
        return _parse_time(_text(spans[0])), _parse_time(_text(spans[1]))
    if len(spans) == 1:
        t = _parse_time(_text(spans[0]))
        return t, t
    txt = _text(td)
    parts = [p.strip() for p in txt.split("-") if p.strip()]
    if len(parts) >= 2:
        return _parse_time(parts[0]), _parse_time(parts[1])
    if len(parts) == 1:
        t = _parse_time(parts[0])
        return t, t
    return None, None


def _parse_days_cell(td: Tag) -> tuple[str, ...]:
    txt = _text(td)
    if not txt:
        return ()
    return tuple(d.strip() for d in txt.split(",") if d.strip())


def _parse_ages_cell(td: Tag) -> tuple[float | None, float | None]:
    m = _AGE_RE.search(_text(td))
    if not m:
        return None, None
    try:
        return float(m.group(1)), float(m.group(2))
    except ValueError:
        return None, None


def _parse_cost_cell(td: Tag) -> tuple[float | None, float | None]:
    m = _COST_RE.search(_text(td))
    if not m:
        return None, None
    try:
        return float(m.group(1)), float(m.group(2))
    except ValueError:
        return None, None


def _availability_state(span: Tag | None) -> str:
    if span is None:
        return "unknown"
    classes = span.get("class") or []
    for c in classes:
        if c.startswith(_AVAIL_PREFIX):
            return c[len(_AVAIL_PREFIX) :].lower()
    return "unknown"


def _cells_by_title(tr: Tag) -> dict[str, Tag]:
    out: dict[str, Tag] = {}
    for td in tr.select("td.label-cell"):
        title = (td.get("data-title") or "").strip()
        if title:
            out[title] = td
    return out


# ---------------------------------------------------------------------------
# Public parser
# ---------------------------------------------------------------------------


def parse_search_html(html: str) -> list[Section]:
    """Return every section found in a WebTrac search-results document.

    The function is tolerant of empty/missing cells; it never raises on
    ordinary parse drift. Callers should treat ``None`` fields as
    unknown rather than absent.
    """
    soup = BeautifulSoup(html, "html.parser")
    sections: list[Section] = []

    for result in soup.select(".result-content"):
        h2 = result.select_one(".result-header h2")
        if h2 is None:
            continue
        name_span = h2.select_one("span")
        id_em = h2.select_one("em")
        program_name = _text(name_span)
        try:
            program_id = int(_text(id_em))
        except ValueError:
            continue

        for tr in result.select("table tbody tr"):
            cells = _cells_by_title(tr)
            if "Description" not in cells:
                continue

            avail_span = cells.get("Availability") and cells["Availability"].select_one(
                ".itemstatus"
            )
            state = _availability_state(avail_span)
            label = _text(avail_span)

            desc_link = cells["Description"].select_one("a")
            section_name = _text(desc_link)
            info_url = (desc_link.get("href") if desc_link else "") or ""
            fmid_match = _FMID_RE.search(info_url)
            try:
                fmid = int(fmid_match.group(1)) if fmid_match else 0
            except ValueError:
                fmid = 0
            if not fmid:
                # fall back to the cart button URL
                cart_a = tr.select_one("td.button-cell--cart a")
                if cart_a:
                    href = cart_a.get("href") or ""
                    m2 = re.search(r"ARFMIDList=(\d+)", href)
                    if m2:
                        try:
                            fmid = int(m2.group(1))
                        except ValueError:
                            pass
            if not fmid:
                continue

            start_date, end_date = (
                _parse_dates_cell(cells.get("Dates")) if "Dates" in cells else (None, None)
            )
            start_time, end_time = (
                _parse_times_cell(cells.get("Times")) if "Times" in cells else (None, None)
            )
            days = _parse_days_cell(cells.get("Days")) if "Days" in cells else ()
            location = _text(cells.get("Location")) if "Location" in cells else ""
            age_min, age_max = (
                _parse_ages_cell(cells.get("Ages")) if "Ages" in cells else (None, None)
            )
            cost_res, cost_non = (
                _parse_cost_cell(cells.get("Cost")) if "Cost" in cells else (None, None)
            )

            sections.append(
                Section(
                    fmid=fmid,
                    program_id=program_id,
                    program_name=program_name,
                    section_name=section_name,
                    availability_state=state,
                    available_for_signup=(state == "available"),
                    availability_label=label or state.title(),
                    start_date=start_date,
                    end_date=end_date,
                    start_time=start_time,
                    end_time=end_time,
                    days=days,
                    location=location,
                    age_min=age_min,
                    age_max=age_max,
                    cost_resident=cost_res,
                    cost_nonresident=cost_non,
                    info_url=info_url,
                    raw={"_parsed_at": datetime.now(timezone.utc).isoformat()},
                )
            )

    return sections


# ---------------------------------------------------------------------------
# Live fetcher
# ---------------------------------------------------------------------------

# Type / category code maps mined from the live <select> elements.
TYPE_CODES: dict[str, str] = {
    "active": "ACTV",
    "aquatic": "AQUA",
    "after_school": "ASP",
    "camp": "Camp",
    "cert": "CERT",
    "general": "General",
    "iwannago": "IWANNAGO",
    "sports": "SPORT",
    "summer_camp": "SUMMERCAMP",
    "swim_lessons": "SWMLS",
    "tennis": "TEN",
}

CATEGORY_CODES: dict[str, str] = {
    "adult": "ADULT",
    "pet": "PET",
    "youth": "YOUTH",
}


def _new_session() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def fetch_search_html(
    *,
    category: str | None = None,
    type_: str | None = None,
    keyword: str | None = None,
    client: httpx.Client | None = None,
) -> str:
    """Fetch one slice of the activity search and return raw HTML.

    Bootstraps a session on the splash page (sets cookies) and then issues
    a GET to ``search.html`` with module=AR plus the requested filters.
    Vermont Systems WebTrac requires no auth for read-only browsing but
    does set session cookies on first hit.
    """
    own_client = client is None
    c = client or _new_session()
    try:
        # Bootstrap: pick up session cookies / CSRF context.
        c.get(SPLASH_URL)
        params: dict[str, str] = {"module": "AR", "Action": "Start", "display": "Detail"}
        if category:
            params["category"] = category
        if type_:
            params["type"] = type_
        if keyword:
            params["keyword"] = keyword
            params["keywordoption"] = "Match One"
        r = c.get(SEARCH_URL, params=params)
        r.raise_for_status()
        return r.text
    finally:
        if own_client:
            c.close()


def fetch_all_sections(
    *,
    categories: Iterable[str] | None = None,
    types: Iterable[str] | None = None,
    client: httpx.Client | None = None,
) -> list[Section]:
    """Pull and parse every (category, type) slice and return a flat list.

    Without a category filter, Vermont Systems WebTrac returns its
    category-picker landing page rather than a results listing. So when
    no categories are passed, we iterate the three published category
    codes (ADULT, PET, YOUTH) — that covers the entire activity
    universe. Sections are deduped by FMID across slices, since a
    single program could in theory appear under multiple categories.
    """
    own_client = client is None
    c = client or _new_session()
    seen_fmids: set[int] = set()
    out: list[Section] = []
    try:
        cats = list(categories) if categories else list(CATEGORY_CODES.values())
        tps = list(types) if types else [None]
        for cat in cats:
            for tp in tps:
                html = fetch_search_html(category=cat, type_=tp, client=c)
                for s in parse_search_html(html):
                    if s.fmid in seen_fmids:
                        continue
                    seen_fmids.add(s.fmid)
                    out.append(s)
        return out
    finally:
        if own_client:
            c.close()


def filter_for_chat(sections: list[Section]) -> list[Section]:
    """Default-visibility filter for the Hava chat layer.

    Drops sections that are not currently signing up (Unavailable, Full,
    Cancelled, Waitlist-only, etc.). The full list — including dropped
    sections — should still be persisted; this filter is applied only
    when the chat layer assembles Context for a generic question.
    """
    return [s for s in sections if s.available_for_signup]
