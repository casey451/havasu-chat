"""
PDF-based parser + fetcher for Lake Havasu City's Aquatic Center schedule.

The city moved the Aquatic Center schedule from inline HTML to two PDF
downloads sometime between 2026-05-07 and 2026-05-21. The previous HTML
URL ``/parks-recreation/open-swim-schedule`` now redirects to
``/329/Aquatic-Center`` (a tabbed landing page with zero parseable
``.sch-day-wrp`` blocks), so ``app.contrib.lhcaz_aquatic`` silently
returned ``[]`` and the ``parks-rec-scrapes`` cron failed for five
consecutive runs (#57-#61). This module is the carry-resolution per
``outputs/lhcaz_aquatic_pdf_rewrite_carry.md``.

Inputs
------
Two PDFs published as DocumentCenter downloads:

  Exercise classes : ``/DocumentCenter/View/7325/Exercise-Class-Schedule-PDF``
  Lap + open swim  : ``/DocumentCenter/View/7326/Lap-and-Open-Swim-Schedule-PDF``

Both PDFs are single-page month grids (Mon-Fri for the exercise PDF,
Sun-Sat for the swim PDF) with one calendar week per row. The day of
the month appears at the top of each cell (e.g., ``5/4``) and each
subsequent line in the cell is a time-range followed by a class title
(and optional instructor name on the exercise PDF):

    5/4
    8:00a--9:00a Motion & Mobility Paula
    8:15--9:15 Aqua Aerobics Margie
    9:30a-10:30a Aqua Aerobics Margie
    ...

Some cells contain ``Pool Closed`` / ``POOL CLOSED`` (with no time) for
whole-day closures. The swim PDF occasionally has a multi-line title
cell (e.g., ``Free Family Swim`` followed by sponsor/limit metadata).

Output contract
---------------
Reuses the existing ``AquaticSlot`` dataclass and ``PUBLIC_CLASS_TYPES``
frozenset from ``app.contrib.lhcaz_aquatic`` so callers (notably
``app.contrib.parks_rec_loader.load_aquatic_records``) work unchanged.
``pull_snapshot()`` returns ``list[dict[str, Any]]`` -- exactly what the
HTML parser used to return -- by concatenating slots from both PDFs.

Class-type classification differs slightly from the HTML version:
the PDFs don't carry CSS-class codes, so we infer from title keywords
(``Lap Swim`` -> ``lap_swim``, ``Open Swim``/``Family Swim`` ->
``open_swim``, ``Pool Closed`` -> ``pool_closed``, everything else
-> ``exercise_class``). The PDF format has no ``private_practice``
content as of May 2026; if Stingrays sessions return, add detection
here.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timezone
from io import BytesIO
from typing import Any

import httpx
import pdfplumber

from app.contrib.lhcaz_aquatic import (
    PUBLIC_CLASS_TYPES,
    AquaticSlot,
    filter_for_chat,
)

# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

# Hardcoded PDF URLs. The page at ``/329/Aquatic-Center`` links to these
# by absolute path. A discovery-mode pass that re-extracts the hrefs from
# the landing page would be more robust but adds an extra fetch +
# selector dependency. Defer unless / until these URLs prove unstable
# (would manifest as 404s from ``fetch_pdf`` -- monitor via the cron).
EXERCISE_PDF_URL = (
    "https://www.lhcaz.gov/DocumentCenter/View/7325/Exercise-Class-Schedule-PDF"
)
SWIM_PDF_URL = (
    "https://www.lhcaz.gov/DocumentCenter/View/7326/Lap-and-Open-Swim-Schedule-PDF"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30.0

__all__ = [
    "EXERCISE_PDF_URL",
    "SWIM_PDF_URL",
    "AquaticSlot",
    "filter_for_chat",
    "parse_schedule_pdf",
    "fetch_pdf",
    "pull_snapshot",
]


# ---------------------------------------------------------------------------
# Parsing helpers (regex + classification)
# ---------------------------------------------------------------------------

_MONTH_LOOKUP: dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_DAY_NAMES: dict[str, str] = {
    "Sun": "SUNDAY", "Mon": "MONDAY", "Tue": "TUESDAY",
    "Wed": "WEDNESDAY", "Thu": "THURSDAY", "Fri": "FRIDAY", "Sat": "SATURDAY",
}

# A cell that starts with ``5/4`` (no leading whitespace after the
# pdfplumber per-line strip we do upstream).
_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})$")

# Time-range pattern. Handles all observed cell formats:
#   8:00a--9:00a   (em-dash, explicit AM both sides)
#   8:15--9:15      (em-dash, no AM/PM marker)
#   9am--10am      (em-dash, whole-word AM)
#   9:30a-10:30a    (hyphen, explicit AM both sides)
#   5-7:45a         (hyphen, start lacks minutes, end has minute + 'a')
#   12-4p           (hyphen, whole-hour PM)
#   12:15--2:00     (em-dash, no AM/PM -- inferred PM via noon heuristic)
#
# The ``(am|pm|a|p)?(?![A-Za-z])`` group is followed by a negative
# lookahead that requires a non-letter character. Without it, the 'a'
# in ``Aqua Aerobics`` right after a closing time (e.g. ``8:15--9:15
# Aqua``) would be greedily consumed as an AM marker and the 'A' in
# 'Aqua' would be stripped from the title.
_TIME_RANGE_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a|p)?(?![A-Za-z])\s*[—–\-]\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a|p)?(?![A-Za-z])",
    re.IGNORECASE,
)


def _normalize_ampm(token: str | None) -> str | None:
    if not token:
        return None
    t = token.lower()
    if t in ("a", "am"):
        return "am"
    if t in ("p", "pm"):
        return "pm"
    return None


def _to_24(hour: int, ampm: str | None) -> int:
    if ampm == "pm" and hour < 12:
        return hour + 12
    if ampm == "am" and hour == 12:
        return 0
    return hour


def _parse_time_range(text: str) -> tuple[time | None, time | None]:
    """Parse a time-range token. Returns ``(start, end)`` or ``(None, None)``.

    Heuristics when am/pm markers are missing:

    1. If both sides explicit: trust the markers.
    2. If one side missing: inherit from the explicit side.
    3. If both missing and start hour == 12: noon (both PM).
    4. If both missing and start hour > end hour (wraps): start AM, end PM.
    5. Otherwise both default to AM.

    These cover all observed cell formats. The ``12:15--2:00`` swim-PDF
    case lands in rule 3 (start hour 12 -> noon). The exercise-PDF
    ``8:15--9:15`` lands in rule 5 (defaults to AM).
    """
    m = _TIME_RANGE_RE.search(text)
    if not m:
        return None, None

    sh = int(m.group(1))
    sm = int(m.group(2) or 0)
    sap = _normalize_ampm(m.group(3))
    eh = int(m.group(4))
    em = int(m.group(5) or 0)
    eap = _normalize_ampm(m.group(6))

    if sap is None and eap is None:
        if sh == 12:
            sap = eap = "pm"
        elif sh > eh:
            sap, eap = "am", "pm"
        else:
            sap = eap = "am"
    elif sap is None:
        sap = eap
    elif eap is None:
        eap = sap

    try:
        return time(_to_24(sh, sap), sm), time(_to_24(eh, eap), em)
    except ValueError:
        return None, None


def _classify_title(title: str) -> str:
    """Return the AquaticSlot.class_type code for a parsed title."""
    low = title.lower()
    if "pool closed" in low:
        return "pool_closed"
    if "lap swim" in low:
        return "lap_swim"
    if "open swim" in low or "family swim" in low:
        return "open_swim"
    return "exercise_class"


def _extract_year(full_text: str, fallback_year: int) -> int:
    """Pull a 4-digit year out of the page text.

    The PDF header carries the year explicitly (``May 2026 ...``). The
    exercise PDF actually renders the month as ``M ay 2026`` due to a
    glyph-kerning artifact, but the year token is intact -- so a plain
    ``\\b20\\d{2}\\b`` match on the first chunk of the page text works
    cleanly. Returns ``fallback_year`` when no year is found.
    """
    m = re.search(r"\b(20\d{2})\b", full_text or "")
    return int(m.group(1)) if m else fallback_year


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

def parse_schedule_pdf(
    pdf_bytes: bytes,
    *,
    today: date | None = None,
) -> list[AquaticSlot]:
    """Parse one Aquatic Center schedule PDF.

    Args:
        pdf_bytes: Raw PDF bytes. Both the exercise and swim PDFs share
            the same single-page month-grid layout and are handled by
            this one parser.
        today: Reference date used as a fallback when the PDF header
            does not contain an explicit year token. Defaults to
            ``date.today()``.

    Returns:
        A list of ``AquaticSlot`` records (including pool_closed rows).
        Filtering to the publicly-visible subset is the caller's
        responsibility -- use ``filter_for_chat`` for the default
        chat-layer view.
    """
    today = today or date.today()
    slots: list[AquaticSlot] = []
    parsed_at = datetime.now(timezone.utc).isoformat()

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        if not pdf.pages:
            return slots
        page = pdf.pages[0]
        full_text = page.extract_text() or ""
        year = _extract_year(full_text, today.year)
        tables = page.extract_tables()
        if not tables:
            return slots
        table = tables[0]
        if not table or len(table) < 2:
            return slots

        # Map column index -> day name from the header row.
        header = [(c or "").strip() for c in table[0]]
        col_to_day: dict[int, str] = {}
        for i, h in enumerate(header):
            for short, long_name in _DAY_NAMES.items():
                if short.lower() in h.lower():
                    col_to_day[i] = long_name
                    break

        # Walk data rows. Each cell is "<M/D>\n<slot1>\n<slot2>..." or empty.
        for row in table[1:]:
            for col_idx, cell in enumerate(row):
                if not cell:
                    continue
                day_name = col_to_day.get(col_idx, "")
                lines = [ln.strip() for ln in cell.split("\n") if ln.strip()]
                if not lines:
                    continue

                # First line is the M/D token (most cells). If not, the
                # cell carries no date and we skip -- shouldn't happen
                # against the city's table layout but defends against
                # PDF re-shapes.
                dm = _DATE_RE.match(lines[0])
                if not dm:
                    continue
                try:
                    slot_date = date(year, int(dm.group(1)), int(dm.group(2)))
                except ValueError:
                    continue
                body_lines = lines[1:]

                slots.extend(
                    _parse_cell_body(
                        body_lines,
                        slot_date=slot_date,
                        day_name=day_name,
                        parsed_at=parsed_at,
                    )
                )
    return slots


def _parse_cell_body(
    body_lines: list[str],
    *,
    slot_date: date,
    day_name: str,
    parsed_at: str,
) -> list[AquaticSlot]:
    """Convert the non-date lines of a cell into AquaticSlot records.

    A line that begins with a time-range pattern starts a new slot. A
    line without a leading time is treated as continuation of the
    previous slot's title (e.g., ``Lap Swim`` followed by ``(3 Lanes)``,
    or ``Free Family Swim`` followed by sponsor metadata). A cell
    whose body is entirely title-only (no time anywhere -- e.g.,
    ``POOL CLOSED`` or ``Pool Closed``) becomes a single whole-day slot.
    """
    out: list[AquaticSlot] = []
    current_title_parts: list[str] = []
    current_time: tuple[time | None, time | None] | None = None

    def flush() -> None:
        nonlocal current_title_parts, current_time
        if current_time is None and not current_title_parts:
            return
        title = " ".join(current_title_parts).strip()
        start, end = (current_time or (None, None))
        if not title and start is None and end is None:
            current_title_parts = []
            current_time = None
            return
        class_type = _classify_title(title)
        all_day = class_type == "pool_closed" and start is None and end is None
        duration: int | None = None
        if start is not None and end is not None:
            s_min = start.hour * 60 + start.minute
            e_min = end.hour * 60 + end.minute
            if e_min >= s_min:
                duration = e_min - s_min
        out.append(
            AquaticSlot(
                slot_date=slot_date,
                day_name=day_name,
                class_type=class_type,
                title=title,
                start_time=start,
                end_time=end,
                duration_minutes=duration,
                all_day=all_day,
                is_public=class_type in PUBLIC_CLASS_TYPES,
                raw={"_parsed_at": parsed_at, "_source": "pdf"},
            )
        )
        current_title_parts = []
        current_time = None

    for ln in body_lines:
        tm = _TIME_RANGE_RE.match(ln)
        if tm:
            flush()
            start, end = _parse_time_range(ln)
            current_time = (start, end)
            title_text = ln[tm.end():].strip()
            if title_text:
                current_title_parts.append(title_text)
        else:
            if current_time is None and not current_title_parts:
                current_time = (None, None)
                current_title_parts.append(ln)
            else:
                current_title_parts.append(ln)
    flush()
    return out


# ---------------------------------------------------------------------------
# Live fetcher + snapshot adapter
# ---------------------------------------------------------------------------

def fetch_pdf(url: str, *, client: httpx.Client | None = None) -> bytes:
    """Fetch a PDF and return raw bytes. Caller owns the client lifecycle
    if one is passed; otherwise we open and close our own.
    """
    own_client = client is None
    c = client or httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    try:
        r = c.get(url)
        r.raise_for_status()
        return r.content
    finally:
        if own_client:
            c.close()


def pull_snapshot() -> list[dict[str, Any]]:
    """Adapter for ``app.contrib.scrape_runner``.

    Fetches both PDFs (exercise classes + lap/open swim) and returns the
    combined list of parsed records as dicts. Includes every parsed
    slot -- public and pool_closed -- so downstream code can
    distinguish. Errors from either fetch are allowed to propagate;
    the scrape runner records the source as failed for that tick.
    """
    today = date.today()
    with httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    ) as client:
        exercise_pdf = fetch_pdf(EXERCISE_PDF_URL, client=client)
        swim_pdf = fetch_pdf(SWIM_PDF_URL, client=client)

    slots: list[AquaticSlot] = []
    slots.extend(parse_schedule_pdf(exercise_pdf, today=today))
    slots.extend(parse_schedule_pdf(swim_pdf, today=today))
    return [s.to_dict() for s in slots]


# vim: set fileencoding=utf-8 :

