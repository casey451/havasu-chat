"""Lake Havasu City Aquatic Center pickleball open-play schedule.

The LHCPBA site publishes open play only inside a JavaScript ``eventscalendar.co``
calendar widget that does not render for a headless scraper, so
:mod:`app.contrib.lakehavasu_pickleball` historically published Aquatic Center
open play as flat **all-day** events with no real hours.

The City of Lake Havasu City, however, publishes the authoritative Aquatic
Center "Open Gym" schedule as a **monthly PDF at a stable URL** (CivicPlus
DocumentCenter id 788). The PDF carries a Sun--Sat day grid with the real
per-day pickleball windows (e.g. ``9:00am - 12:00pm`` / ``12:30pm - 3:30pm``),
distinguishes Pickleball / Basketball / "Closed For Event", and flags special
sessions ("ROUND ROBIN (Must Pre-Register)", "GLOW Pickleball").

This module fetches that PDF and parses it into **timed**
:class:`~app.contrib.lakehavasu_pickleball.EventSpec` rows, so the loader
publishes real start/end times instead of all-day placeholders. pdfplumber's
table extraction groups each day into one bordered cell (number + activity +
times); a plain-text parser is kept as a fallback. Because the URL is stable
and the PDF refreshes monthly, the existing scraper cron keeps the times current
with no browser and no manual capture.
"""

from __future__ import annotations

import io
import logging
import re
from datetime import date

import httpx

from app.contrib.lakehavasu_pickleball import (
    REQUEST_TIMEOUT,
    USER_AGENT,
    EventSpec,
)

logger = logging.getLogger(__name__)

# Stable CivicPlus document URL: always serves the current month's Open Gym
# schedule (the bare default-source path and the ?sfvrsn= variants are not
# stable; the DocumentCenter id is).
AQUATIC_SCHEDULE_URL = "https://www.lhcaz.gov/DocumentCenter/View/788/Open-Gym-Schedule-PDF"
AQUATIC_VENUE_NAME = "Lake Havasu City Aquatic Center"
AQUATIC_COST = "$3.00 per participant (pay at the cashier counter)"

_MONTHS: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

_YEAR_RE = re.compile(r"Revised\s+\d{1,2}/\d{1,2}/(\d{4})")
_MONTH_RE = re.compile(r"Open Gym\s+([A-Za-z]+)\s+Schedule", re.I)
# A new day cell: a bare day number, or a day number immediately followed by an
# activity keyword (pdfplumber sometimes merges them). The keyword guard stops
# "18 & up" (basketball age text) from being misread as day 18.
_DAY_BARE_RE = re.compile(r"^(\d{1,2})$")
_DAY_INLINE_RE = re.compile(r"^(\d{1,2})\s+(Pickleball|Basketball|Closed|GLOW)\b", re.I)
# "9:00am - 12:00pm" with any dash variant; am/pm tolerant of dots.
_RANGE_RE = re.compile(
    r"(\d{1,2}):(\d{2})\s*([ap])\.?m\.?\s*[—–-]\s*"
    r"(\d{1,2}):(\d{2})\s*([ap])\.?m\.?",
    re.I,
)


def _to_24h(hour: str, minute: str, ampm: str) -> str:
    h = int(hour)
    ap = ampm.lower()
    if ap == "p" and h != 12:
        h += 12
    elif ap == "a" and h == 12:
        h = 0
    return f"{h:02d}:{minute}"


def _time_ranges(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in _RANGE_RE.finditer(text):
        start = _to_24h(m.group(1), m.group(2), m.group(3))
        end = _to_24h(m.group(4), m.group(5), m.group(6))
        out.append((start, end))
    return out


def _kind(text: str) -> tuple[str, str]:
    """(title_prefix, note) for a pickleball day, by sub-type."""
    low = text.lower()
    if "round robin" in low:
        return "Pickleball Round Robin", "Member round robin -- must pre-register."
    if "glow" in low:
        return "GLOW Pickleball", "Special GLOW (lights-down) pickleball session."
    return "Pickleball Open Play", "Drop-in open play."


def _parse_year_month(text: str) -> tuple[int, int] | None:
    """(year, month) from the PDF header, or None if absent."""
    ym = _YEAR_RE.search(text)
    mm = _MONTH_RE.search(text)
    if not ym or not mm:
        return None
    month = _MONTHS.get(mm.group(1).lower())
    if not month:
        return None
    return int(ym.group(1)), month


def _specs_for_cell(cell: str, *, year: int, month: int) -> list[EventSpec]:
    """Pickleball EventSpecs for one calendar day cell, or [] if not pickleball.

    A cell is the full text of one day box, e.g.
    ``"2\\nPickleball\\n9:00am - 12:00pm\\n12:30pm - 3:30pm"``. Basketball and
    "Closed For Event" cells yield []. Two windows -> two specs."""
    c = (cell or "").strip()
    m = re.match(r"(\d{1,2})\b", c)
    if not m:
        return []
    day = int(m.group(1))
    if not (1 <= day <= 31) or "pickleball" not in c.lower():
        return []
    ranges = _time_ranges(c)
    if not ranges:
        return []
    try:
        day_date = date(year, month, day)
    except ValueError:
        return []
    prefix, note = _kind(c)
    out: list[EventSpec] = []
    for start, end in ranges:
        desc = (
            f"{note} {prefix} at {AQUATIC_VENUE_NAME} "
            f"({start}-{end}). Cost: {AQUATIC_COST}. "
            "Source: City of Lake Havasu City Aquatic Center Open Gym schedule."
        )
        out.append(
            EventSpec(
                title=f"{prefix} - {AQUATIC_VENUE_NAME}"[:300],
                description=desc,
                date=day_date,
                end_date=day_date,
                location_name=AQUATIC_VENUE_NAME,
                event_url=AQUATIC_SCHEDULE_URL,
                source_anchor=f"openplay|aquatic|{day_date.isoformat()}|{start}",
                all_day=False,
                start_time=start,
                end_time=end,
            )
        )
    return out


def parse_aquatic_cells(cells: list[str], *, year: int, month: int) -> list[EventSpec]:
    """Parse pickleball day cells (from pdfplumber table extraction)."""
    specs: list[EventSpec] = []
    for cell in cells:
        specs.extend(_specs_for_cell(cell, year=year, month=month))
    return specs


def parse_aquatic_open_gym(pdf_text: str) -> list[EventSpec]:
    """Parse the City Open Gym PDF text into timed pickleball ``EventSpec`` rows.

    Only days whose cell mentions pickleball are emitted; Basketball and
    "Closed For Event" days are skipped. A day with two windows yields two specs.
    Returns ``[]`` if the year/month header can't be read (caller falls back).
    """
    ym = _parse_year_month(pdf_text)
    if not ym:
        return []
    year, month = ym

    blocks: list[tuple[int, list[str]]] = []
    last = 0
    cur: list[str] | None = None
    started = False
    for raw in pdf_text.splitlines():
        ln = raw.strip()
        if not started:
            if ln.startswith("Sun") and "Mon" in ln and "Sat" in ln:
                started = True
            continue
        if "Open Gym Schedule is for" in ln or _MONTH_RE.search(ln):
            break  # footer / title block after the grid
        bare = _DAY_BARE_RE.match(ln)
        inline = _DAY_INLINE_RE.match(ln)
        if bare and 1 <= int(bare.group(1)) <= 31 and int(bare.group(1)) > last:
            last = int(bare.group(1))
            cur = []
            blocks.append((last, cur))
            continue
        if inline and 1 <= int(inline.group(1)) <= 31 and int(inline.group(1)) > last:
            last = int(inline.group(1))
            cur = [ln[inline.end(1):].strip()]
            blocks.append((last, cur))
            continue
        if cur is not None and ln:
            cur.append(ln)

    specs: list[EventSpec] = []
    for day, content in blocks:
        text = " ".join(content)
        if "pickleball" not in text.lower():
            continue
        ranges = _time_ranges(text)
        if not ranges:
            continue
        try:
            day_date = date(year, month, day)
        except ValueError:
            continue
        prefix, note = _kind(text)
        for start, end in ranges:
            desc = (
                f"{note} {prefix} at {AQUATIC_VENUE_NAME} "
                f"({start}-{end}). Cost: {AQUATIC_COST}. "
                "Source: City of Lake Havasu City Aquatic Center Open Gym schedule."
            )
            specs.append(
                EventSpec(
                    title=f"{prefix} - {AQUATIC_VENUE_NAME}"[:300],
                    description=desc,
                    date=day_date,
                    end_date=day_date,
                    location_name=AQUATIC_VENUE_NAME,
                    event_url=AQUATIC_SCHEDULE_URL,
                    source_anchor=f"openplay|aquatic|{day_date.isoformat()}|{start}",
                    all_day=False,
                    start_time=start,
                    end_time=end,
                )
            )
    return specs


def _fetch_pdf_bytes(url: str, *, client: httpx.Client | None) -> bytes:
    if client is None:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as c:
            return _fetch_pdf_bytes(url, client=c)
    resp = client.get(url)
    resp.raise_for_status()
    return resp.content


def fetch_aquatic_open_play(*, client: httpx.Client | None = None) -> list[EventSpec]:
    """Fetch + parse the City Open Gym PDF into timed Aquatic Center specs.

    pdfplumber's table extraction groups each day into one bordered cell (number
    + activity + times), which is reliable for this calendar grid. We parse those
    cells; if no table is detected we fall back to the plain-text parser."""
    import pdfplumber

    data = _fetch_pdf_bytes(AQUATIC_SCHEDULE_URL, client=client)
    cells: list[str] = []
    text = ""
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text += (page.extract_text() or "") + "\n"
            for table in page.extract_tables() or []:
                for row in table:
                    for cell in row:
                        if cell:
                            cells.append(cell)
    ym = _parse_year_month(text)
    specs: list[EventSpec] = []
    if ym:
        specs = parse_aquatic_cells(cells, year=ym[0], month=ym[1])
    used = "table"
    if not specs:
        specs = parse_aquatic_open_gym(text)
        used = "text-fallback"
    logger.info(
        "aquatic open-gym: %d table cells -> %d timed specs (via %s)",
        len(cells), len(specs), used,
    )
    return specs
