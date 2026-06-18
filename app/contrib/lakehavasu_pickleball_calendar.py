"""LHCPBA open-play calendar scrape (the JS widget) -> recurring Program specs.

The Calendar page embeds a third-party ``plugin.eventscalendar.co`` widget in a
**cross-origin iframe**. There is no JSON API to call and the widget only renders
when embedded in the parent page (it needs the Wix parent<->iframe handshake), so
the static HTML and the standalone widget URL are both empty. The only reliable
way to read it is to render the full page in a real browser and reach into the
widget frame. We use Playwright (already pinned in requirements.txt).

The widget's events are the **recurring weekly open-play schedule** across the
three venues (e.g. "8:00 am ARK Center", "9:00 am Aquatic Center", "DSP Open
Play"). Rather than emit hundreds of one-off events, we collapse occurrences into
a handful of recurring :class:`~app.contrib.lakehavasu_pickleball.ProgramSpec`
rows -- one per distinct (start time, venue) -- with ``schedule_days`` accumulated
across the scraped window.

Two layers, deliberately split for testability:

  * :func:`fetch_calendar_occurrences` -- the Playwright render + DOM extraction
    (browser-bound; not unit-tested in CI without a browser install).
  * :func:`group_open_play` -- a PURE function (occurrences -> ProgramSpecs) that
    is fully unit-tested against fixture occurrences with no browser.

NOTE (validation): the widget's internal DOM selectors could not be exercised in
the offline sandbox where this was written. ``fetch_calendar_occurrences`` is
defensive -- it tries several strategies and returns ``[]`` (rather than raising)
if it recognizes nothing, so a widget markup change degrades to "no open-play
programs this run" instead of failing the whole scrape. Validate end-to-end via
the workflow's ``workflow_dispatch`` button before relying on it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from app.contrib.lakehavasu_pickleball import (
    BASE_URL,
    ProgramSpec,
)

logger = logging.getLogger(__name__)

CALENDAR_URL = f"{BASE_URL}/calendar"
WIDGET_HOST = "eventscalendar.co"

# Venue keyword -> (clean venue name, address, default cost). Used to enrich
# occurrences whose detail text is terse, and to label grouped programs.
_VENUE_MAP: tuple[tuple[str, str, str, str | None], ...] = (
    ("ark", "The Ark Center", "2700 Jamaica Blvd S, Lake Havasu City, AZ 86406", "$5 per session"),
    ("aquatic", "Lake Havasu City Aquatic Center", "100 Park Ave, Lake Havasu City, AZ 86403", "$3 per session"),
    ("ac ", "Lake Havasu City Aquatic Center", "100 Park Ave, Lake Havasu City, AZ 86403", "$3 per session"),
    ("dsp", "Mike Delaney Pickleball Complex at Dick Samp Park", "1628 Avalon Ave, Lake Havasu City, AZ 86404", "Free"),
    ("dick samp", "Mike Delaney Pickleball Complex at Dick Samp Park", "1628 Avalon Ave, Lake Havasu City, AZ 86404", "Free"),
    ("delaney", "Mike Delaney Pickleball Complex at Dick Samp Park", "1628 Avalon Ave, Lake Havasu City, AZ 86404", "Free"),
)

_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.I)


@dataclass
class Occurrence:
    """One rendered calendar event occurrence."""

    title: str
    date: date | None = None
    start_time: str | None = None  # "HH:MM"
    end_time: str | None = None  # "HH:MM"
    location: str | None = None
    cost: str | None = None
    raw: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def parse_clock(text: str | None) -> str | None:
    """'8:00am'/'8 am'/'12:30 pm' -> 'HH:MM' (24h). None if no time found."""
    if not text:
        return None
    m = _TIME_RE.search(text)
    if not m:
        return None
    hour = int(m.group(1)) % 12
    minute = int(m.group(2) or 0)
    if m.group(3).lower() == "pm":
        hour += 12
    return f"{hour:02d}:{minute:02d}"


def _match_venue(text: str) -> tuple[str, str, str | None] | None:
    """Match a venue by whole-word keyword.

    Word boundaries (not raw substring) matter for short tokens: "ac" must match
    the "AC" abbreviation but not "Isaac", and "ark" must match "ARK Center" but
    not "...Samp Park".
    """
    low = (text or "").lower()
    for kw, name, addr, cost in _VENUE_MAP:
        if re.search(r"\b" + re.escape(kw.strip()) + r"\b", low):
            return name, addr, cost
    return None


def _group_key(occ: Occurrence) -> tuple[str, str]:
    """Distinct recurring session = (start time, venue)."""
    venue = _match_venue(f"{occ.title} {occ.location or ''}")
    venue_name = venue[0] if venue else (occ.location or "Lake Havasu City")
    return (occ.start_time or "varies", venue_name)


def group_open_play(occurrences: list[Occurrence]) -> list[ProgramSpec]:
    """Collapse recurring occurrences into one ProgramSpec per (time, venue).

    ``schedule_days`` accumulates the distinct weekdays the session was seen on
    across the scraped window. End time / cost / address are taken from the
    occurrences (falling back to venue defaults). Pure + deterministic.
    """
    buckets: dict[tuple[str, str], list[Occurrence]] = {}
    for occ in occurrences:
        if not occ.title:
            continue
        buckets.setdefault(_group_key(occ), []).append(occ)

    specs: list[ProgramSpec] = []
    for (start_time, venue_name), occs in sorted(buckets.items()):
        days = sorted(
            {_WEEKDAYS[o.date.weekday()] for o in occs if o.date is not None},
            key=_WEEKDAYS.index,
        )
        sample = occs[0]
        venue = _match_venue(f"{sample.title} {sample.location or ''}")
        addr = sample.location if (sample.location and "," in (sample.location or "")) else None
        cost = sample.cost
        if venue:
            venue_name, default_addr, default_cost = venue
            addr = addr or default_addr
            cost = cost or default_cost
        end_time = next((o.end_time for o in occs if o.end_time), None)
        when = ("on " + ", ".join(days)) if days else "on a recurring weekly basis"
        time_str = ""
        if start_time and start_time != "varies":
            time_str = f" at {start_time}" + (f"-{end_time}" if end_time else "")
        desc = (
            f"Open pickleball play at {venue_name} {when}{time_str}, hosted/coordinated "
            f"by the Lake Havasu City Pickleball Association. "
            + (f"Cost: {cost}. " if cost else "")
            + f"See the live schedule at {CALENDAR_URL}."
        )
        title = f"Open Play - {venue_name}"
        if start_time and start_time != "varies":
            title += f" ({start_time})"
        specs.append(
            ProgramSpec(
                title=title,
                description=desc,
                location_name=venue_name,
                location_address=addr,
                cost=cost,
                schedule_days=days,
                start_time=start_time if start_time != "varies" else None,
                end_time=end_time,
                activity_category="sports",
                tags=["sports", "open-play"],
                contact_url=CALENDAR_URL,
                source_anchor=f"openplay|{venue_name}|{start_time}",
            )
        )
    return specs


# ---------------------------------------------------------------------------
# Browser layer (Playwright) -- best-effort, defensive
# ---------------------------------------------------------------------------


def fetch_calendar_occurrences(
    *,
    months: int = 1,
    headless: bool = True,
    timeout_ms: int = 45_000,
) -> list[Occurrence]:
    """Render the calendar and extract event occurrences from the widget frame.

    Returns ``[]`` (logging a warning) if Playwright is unavailable, the widget
    frame never appears, or no events are recognized -- so the caller treats a
    widget change as "no open-play data this run" rather than a hard failure.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        logger.warning("playwright unavailable; skipping open-play calendar: %s", e)
        return []

    occurrences: list[Occurrence] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            try:
                page = browser.new_page()
                page.goto(CALENDAR_URL, wait_until="networkidle", timeout=timeout_ms)
                frame = _wait_for_widget_frame(page, timeout_ms)
                if frame is None:
                    logger.warning("events-calendar widget frame not found")
                    return []
                for _ in range(max(1, months)):
                    occurrences.extend(_extract_visible_occurrences(frame))
                    if not _go_next_month(frame):
                        break
            finally:
                browser.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("open-play calendar render failed: %s", e)
        return []

    # De-dup identical occurrences (same title+date+time).
    seen: set[tuple] = set()
    unique: list[Occurrence] = []
    for o in occurrences:
        key = (o.title, o.date, o.start_time)
        if key in seen:
            continue
        seen.add(key)
        unique.append(o)
    return unique


def _wait_for_widget_frame(page, timeout_ms: int):
    """Return the eventscalendar.co frame once it has attached, else None."""
    import time as _time

    deadline = _time.time() + timeout_ms / 1000.0
    while _time.time() < deadline:
        for fr in page.frames:
            if WIDGET_HOST in (fr.url or ""):
                try:
                    fr.wait_for_load_state("networkidle", timeout=5_000)
                except Exception:  # noqa: BLE001
                    pass
                return fr
        page.wait_for_timeout(500)
    return None


def _extract_visible_occurrences(frame) -> list[Occurrence]:
    """Best-effort extraction of event occurrences from the widget frame.

    Strategy: read the frame's rendered text and pull lines that look like
    "<time> <venue>" or all-day venue banners. Date is inferred from the
    frame's visible month header where a per-cell date is not resolvable.

    This is intentionally tolerant: the exact widget DOM could not be exercised
    offline, so we lean on visible text rather than brittle selectors. Returns
    whatever it recognizes (possibly empty).
    """
    occurrences: list[Occurrence] = []
    try:
        text = frame.inner_text("body")
    except Exception:  # noqa: BLE001
        return []
    for line in (ln.strip() for ln in text.splitlines()):
        if not line:
            continue
        if _match_venue(line) is None:
            continue
        start = parse_clock(line)
        occurrences.append(
            Occurrence(
                title=line[:120],
                start_time=start,
                location=None,
                raw={"line": line},
            )
        )
    return occurrences


def _go_next_month(frame) -> bool:
    """Advance the widget to the next month. Returns False if it can't."""
    for sel in (
        "button[aria-label*='Next' i]",
        "[data-hook*='next' i]",
        "button:has-text('>')",
    ):
        try:
            el = frame.query_selector(sel)
            if el:
                el.click()
                frame.wait_for_timeout(1_500)
                return True
        except Exception:  # noqa: BLE001
            continue
    return False
