"""Havasu Lanes scraper — keep the bowling alley's Rock & Bowl / Cosmic Bowling
nights fresh from the venue's own site instead of hand-loading static dated rows
that expire.

Two static pages, parsed from page TEXT (robust to DOM churn):

  * ``https://havasulanesaz.com/``         -> "Hours of Operation" (Mon-Thu
    12-9, Fri-Sat 12-11, Sun 12-7).
  * ``https://havasulanesaz.com/SPECIALS`` -> "ROCK & BOWL EVERY FRIDAY &
    SATURDAY NIGHT 6PM TO CLOSE" + pricing ($18/$22/$26 incl. shoes + 1/2/3 hrs).

Pure parsers here; the loader (:mod:`scripts.havasu_lanes_load`) owns the network
fetch + persistence. The themed nights publish as dated, timed **"Cosmic
Bowling"** Event occurrences on each matching weekday in a rolling forward window,
reusing the funzone :class:`~app.contrib.lhc_funzone.FunEventSpec` carrier. They
use the SAME ``rock-and-bowl-<date>`` ``source_url`` the existing catalog rows
use, so a re-run is idempotent (dedups against live rows) and only adds NEW future
dates.

Honesty contract (mirrors ``family_venues.py``): a night is published only if the
SPECIALS page still says it. A parse miss publishes nothing — the last-good rows
stand until they age out — and the loader logs a freshness warning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

from app.contrib.lhc_funzone import FunEventSpec

SOURCE_NAME = "havasu_lanes"
BASE_URL = "https://havasulanesaz.com/"
SPECIALS_URL = "https://havasulanesaz.com/SPECIALS"
LOCATION_NAME = "Havasu Lanes"
EVENT_TITLE = "Cosmic Bowling"

# The dated rows already in the catalog use this slug scheme; matching it keeps
# the scraper idempotent against them (no duplicate twin per date).
OCC_URL = "https://www.havasulanesaz.com/specials?occ=rock-and-bowl-{day}"

# Publish ~8 weeks of upcoming nights; the twice-weekly cron keeps extending the
# window and the loader prunes rows as they age, so it never runs dry.
WINDOW_DAYS = 56
# Fri/Sat close is 11 PM per the hours page; "to close" maps here.
DEFAULT_CLOSE = "23:00"

# Clean, all-ages tags (Casey 2026-06-26: glow bowling is an all-ages venue event,
# NOT youth — see app.events.family_filter.is_youth_event). No "kids"/youth tag.
EVENT_TAGS: tuple[str, ...] = ("activity:bowling", "facet:special", "glow", "all ages", "family")

_USER_AGENT = "AskHavaBot/1.0 (+https://askhava.com; Lake Havasu local directory)"
_WEEKDAYS: dict[str, int] = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?", re.IGNORECASE)


@dataclass(frozen=True)
class RockAndBowl:
    """The parsed Rock & Bowl special."""

    weekdays: tuple[int, ...]  # Monday=0 .. Sunday=6, e.g. (4, 5) = Fri & Sat
    start: str                 # "HH:MM"
    end: str | None            # "HH:MM" close, or None
    pricing: str | None        # human-readable price line(s), if found


def fetch(url: str, *, timeout: float = 30.0) -> str:
    """GET a Havasu Lanes page (network; not used by the unit tests)."""
    resp = requests.get(
        url, headers={"User-Agent": _USER_AGENT, "Accept": "text/html"}, timeout=timeout
    )
    resp.raise_for_status()
    return resp.text


def visible_text(html: str) -> str:
    """Tag-stripped, whitespace-collapsed page text (parse target)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def _to_hhmm(m: re.Match[str]) -> str:
    hour = int(m.group(1)) % 12
    minute = int(m.group(2) or 0)
    if m.group(3).lower() == "p":
        hour += 12
    return f"{hour:02d}:{minute:02d}"


def parse_rock_and_bowl(text: str) -> RockAndBowl | None:
    """Parse the Rock & Bowl night from the SPECIALS page text. Returns None when
    the special isn't found (the caller must then publish nothing)."""
    low = text.lower()
    m = re.search(r"rock\s*(?:&|and|'?n)?\s*bowl", low)
    if not m:
        return None
    # Look at the run of text right after the "Rock & Bowl" headline (the days +
    # time live there: "EVERY FRIDAY & SATURDAY NIGHT 6PM TO CLOSE").
    seg = low[m.start(): m.start() + 160]
    weekdays = tuple(sorted({wd for name, wd in _WEEKDAYS.items() if name in seg}))
    if not weekdays:
        return None
    times = list(_TIME_RE.finditer(seg))
    if not times:
        return None
    start = _to_hhmm(times[0])
    if "close" in seg or "midnight" in seg:
        end: str | None = DEFAULT_CLOSE
    elif len(times) >= 2:
        end = _to_hhmm(times[1])
    else:
        end = DEFAULT_CLOSE
    return RockAndBowl(weekdays=weekdays, start=start, end=end, pricing=_parse_pricing(text))


def _parse_pricing(text: str) -> str | None:
    """Join the "$NN ... includes ... bowling" price lines, if present."""
    prices = re.findall(
        r"\$\d{1,3}[^.]*?\bincludes\b[^.]*?\bbowling\b", text, flags=re.IGNORECASE
    )
    return " ".join(p.strip() for p in prices) or None


def _description(special: RockAndBowl) -> str:
    bits = [
        "Rock & Bowl glow bowling at Havasu Lanes — lights down, black-lights, "
        "party lights and all your favorite music."
    ]
    if special.pricing:
        bits.append(special.pricing)
    bits.append(f"See {SPECIALS_URL}.")
    return " ".join(bits)


def cosmic_bowling_specs(
    special: RockAndBowl | None,
    *,
    today: date | None = None,
    window_days: int = WINDOW_DAYS,
) -> list[FunEventSpec]:
    """Dated "Cosmic Bowling" occurrences for each matching weekday in the window.

    Empty when ``special`` is None (parse miss → publish nothing, honesty
    contract). The ``source_url`` (built from ``event_url``) matches the existing
    catalog rows so re-runs dedupe instead of duplicating.
    """
    if special is None:
        return []
    today = today or date.today()
    desc = _description(special)
    specs: list[FunEventSpec] = []
    for offset in range(max(1, window_days)):
        d = today + timedelta(days=offset)
        if d.weekday() not in special.weekdays:
            continue
        specs.append(
            FunEventSpec(
                title=EVENT_TITLE,
                description=desc,
                date=d,
                end_date=d,
                location_name=LOCATION_NAME,
                event_url=OCC_URL.format(day=d.isoformat()),
                source_anchor=f"rock-and-bowl-{d.isoformat()}",
                tags=list(EVENT_TAGS),
                all_day=False,
                start_time=special.start,
                end_time=special.end,
            )
        )
    return specs


def scrape_specs(
    *, today: date | None = None, window_days: int = WINDOW_DAYS
) -> list[FunEventSpec]:
    """Fetch the live SPECIALS page and return dated Cosmic Bowling specs. Network
    failures and parse misses both yield an empty list (publish nothing)."""
    try:
        html = fetch(SPECIALS_URL)
    except requests.RequestException:
        return []
    special = parse_rock_and_bowl(visible_text(html))
    return cosmic_bowling_specs(special, today=today, window_days=window_days)
