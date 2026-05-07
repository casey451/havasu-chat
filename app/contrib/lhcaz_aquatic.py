"""
Parser + fetcher for Lake Havasu City's Aquatic Center weekly schedule.

Source: ``https://www.lhcaz.gov/parks-recreation/open-swim-schedule``

The page is a Sitefinity-rendered static document. Each day is a
``div.sch-day-wrp`` block; each scheduled cell inside is a
``div.sch-XXX sch-YY sch-cell`` where ``XXX`` is duration in minutes
(or ``full`` for all-day) and ``YY`` is the class-type code:

    sch-ls  → Lap Swim
    sch-ex  → Exercise class (Fit & Flex, Aqua Aerobics, etc.)
    sch-os  → Open Swim
    sch-pc  → Pool Closed
    sch-sr  → Stingrays private practice (NOT open to the public)

The page only carries month/day on each header (e.g. "MAY 7"), no year.
``parse_schedule_html(html, today)`` infers the year from the supplied
reference date — if the parsed month/day is more than 30 days behind
``today``, it rolls to the next year.

Each row produced by ``parse_schedule_html`` is a single date+time slot
("AquaticSlot") rather than a recurring program: the city republishes
this page every couple of weeks, so the catalog gets concrete dates.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timezone
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30.0
SCHEDULE_URL = "https://www.lhcaz.gov/parks-recreation/open-swim-schedule"

CLASS_TYPE_BY_CODE: dict[str, str] = {
    "ls": "lap_swim",
    "ex": "exercise_class",
    "os": "open_swim",
    "pc": "pool_closed",
    "sr": "private_practice",
}

# What shows up in the chat by default. "pool_closed" is implicitly
# excluded — those rows convey absence, not an offering. "private_practice"
# is explicitly tagged "not open to the public" by the venue, so the
# default chat-layer view drops them.
PUBLIC_CLASS_TYPES: frozenset[str] = frozenset({"lap_swim", "exercise_class", "open_swim"})


@dataclass(frozen=True)
class AquaticSlot:
    slot_date: date
    day_name: str                  # "THURSDAY", "FRIDAY", ...
    class_type: str                # "lap_swim" / "exercise_class" / ...
    title: str                     # "Lap Swim", "Aqua Aerobics", ...
    start_time: time | None
    end_time: time | None
    duration_minutes: int | None   # parsed from sch-XXX prefix, None for "full"
    all_day: bool
    is_public: bool                # default-visible in chat?
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["slot_date"] = self.slot_date.isoformat() if self.slot_date else None
        out["start_time"] = self.start_time.isoformat() if self.start_time else None
        out["end_time"] = self.end_time.isoformat() if self.end_time else None
        out.pop("raw", None)
        return out


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_MONTH_LOOKUP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

_DURATION_RE = re.compile(r"sch-(\d+)\b")
_TYPE_RE = re.compile(r"sch-(ls|ex|os|pc|sr)\b")
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(am|pm)", re.IGNORECASE)
_DATE_RE = re.compile(r"\b([A-Z]{3,9})\s+(\d{1,2})\b")


def _text(tag: Tag | None) -> str:
    return tag.get_text(" ", strip=True) if tag else ""


def _parse_time(s: str) -> time | None:
    m = _TIME_RE.search(s)
    if not m:
        return None
    h, mn, ap = int(m.group(1)), int(m.group(2)), m.group(3).lower()
    if ap == "pm" and h != 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    try:
        return time(h, mn)
    except ValueError:
        return None


def _parse_time_range(s: str) -> tuple[time | None, time | None, bool]:
    """Return (start, end, all_day). Handles 'All day' and 'X - End of Day'."""
    s = s.strip()
    if not s:
        return None, None, False
    if "all day" in s.lower():
        return None, None, True
    if "end of day" in s.lower():
        # "4:00 pm - End of Day"
        start = _parse_time(s.split("-")[0]) if "-" in s else _parse_time(s)
        return start, None, False
    parts = [p.strip() for p in s.split("-") if p.strip()]
    if len(parts) >= 2:
        return _parse_time(parts[0]), _parse_time(parts[1]), False
    if len(parts) == 1:
        t = _parse_time(parts[0])
        return t, t, False
    return None, None, False


def _infer_year(month: int, day: int, today: date) -> int:
    """Best-effort year inference for a month/day from the page header.

    The schedule page never displays the year. We assume the page shows
    current and near-future dates: parse with ``today.year`` first, and
    if the result is more than 30 days in the past, bump to next year.
    """
    try:
        candidate = date(today.year, month, day)
    except ValueError:
        return today.year
    if (today - candidate).days > 30:
        return today.year + 1
    return today.year


def _parse_day_header(span_day: Tag | None, span_date: Tag | None, today: date) -> tuple[str, date | None]:
    day_name = _text(span_day).upper()
    raw = _text(span_date)
    m = _DATE_RE.search(raw)
    if not m:
        return day_name, None
    mon_token, day_token = m.group(1).upper()[:3], int(m.group(2))
    month = _MONTH_LOOKUP.get(mon_token)
    if not month:
        return day_name, None
    return day_name, date(_infer_year(month, day_token, today), month, day_token)


def _classify_cell(cell: Tag) -> tuple[str | None, int | None]:
    classes = " ".join(cell.get("class") or [])
    type_match = _TYPE_RE.search(classes)
    dur_match = _DURATION_RE.search(classes)
    code = type_match.group(1) if type_match else None
    duration: int | None = None
    if dur_match:
        try:
            duration = int(dur_match.group(1))
        except ValueError:
            duration = None
    elif "sch-full" in classes:
        duration = None  # full-day; no minute count
    return code, duration


# ---------------------------------------------------------------------------
# Public parser
# ---------------------------------------------------------------------------

def parse_schedule_html(html: str, *, today: date | None = None) -> list[AquaticSlot]:
    if today is None:
        today = date.today()
    soup = BeautifulSoup(html, "html.parser")
    slots: list[AquaticSlot] = []

    for day_wrp in soup.select(".sch-day-wrp"):
        date_wrp = day_wrp.select_one(".sch-date-wrp")
        if date_wrp is None:
            continue
        day_name, slot_date = _parse_day_header(
            date_wrp.select_one(".sch-day"),
            date_wrp.select_one(".sch-date"),
            today,
        )
        if slot_date is None:
            continue

        for cell in day_wrp.select(".sch-cell"):
            code, duration = _classify_cell(cell)
            if code is None:
                continue
            class_type = CLASS_TYPE_BY_CODE.get(code, "unknown")
            title = _text(cell.select_one(".sch-title"))
            time_text = _text(cell.select_one(".sch-time"))
            start, end, all_day = _parse_time_range(time_text)
            slots.append(
                AquaticSlot(
                    slot_date=slot_date,
                    day_name=day_name,
                    class_type=class_type,
                    title=title,
                    start_time=start,
                    end_time=end,
                    duration_minutes=duration,
                    all_day=all_day,
                    is_public=(class_type in PUBLIC_CLASS_TYPES),
                    raw={"_parsed_at": datetime.now(timezone.utc).isoformat()},
                )
            )
    return slots


def filter_for_chat(slots: list[AquaticSlot]) -> list[AquaticSlot]:
    """Default visibility for the Hava chat layer.

    Drops Pool Closed and Private Practice rows. Keeps lap swim, open
    swim, and exercise classes. The full snapshot — including dropped
    rows — is still persisted so the chat can answer carve-out
    questions ("is the pool closed Sunday?").
    """
    return [s for s in slots if s.is_public]


# ---------------------------------------------------------------------------
# Live fetcher / snapshot adapter
# ---------------------------------------------------------------------------

def fetch_schedule_html(*, client: httpx.Client | None = None) -> str:
    own_client = client is None
    c = client or httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    try:
        r = c.get(SCHEDULE_URL)
        r.raise_for_status()
        return r.text
    finally:
        if own_client:
            c.close()


def pull_snapshot() -> list[dict[str, Any]]:
    """Adapter for ``app.contrib.scrape_runner``.

    Fetches the live page and returns a list of dict records. Includes
    every parsed slot — public and private — so downstream code can
    distinguish.
    """
    html = fetch_schedule_html()
    return [s.to_dict() for s in parse_schedule_html(html)]
