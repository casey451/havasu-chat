"""Lake Havasu Senior Center schedule collector (weekly loader source).

The Senior Center (450 Acoma Blvd S) publishes its schedule on
``lakehavasuseniorcenter.com`` as two MONTHLY IMAGE calendars -- a daily lunch
menu and a weekly activities grid -- plus a "Current Events" page that carries
dated special events (some as prose headings, some as flyer images). Images are
not machine-readable, so this module is the curated + live hybrid that feeds the
**Seniors** section of the events calendar:

* :data:`RECURRING_ACTIVITIES` -- the weekly activities, transcribed from the
  center's published Weekly Activities Calendar. Each becomes a recurring
  ``Event`` with an ``rrule`` so it expands across the calendar. **Edit this
  table when the center changes its weekly schedule.**
* :data:`COMMUNITY_LUNCH` -- the weekday Meals-on-Wheels community lunch.
* :data:`CURATED_SPECIAL_EVENTS` -- dated specials that the center posts as
  FLYER IMAGES (which the text parser can't read). Add new flyers here; past
  ones drop off automatically. **Update when the center posts new flyers.**
* :func:`parse_special_events` -- dated specials posted as page TEXT, scraped
  live each run so text-based seminars appear with no code change.

Everything is emitted as :class:`SeniorEventSpec` and persisted as
``senior``-tagged ``Event`` rows by ``scripts/load_senior_center.py`` (recurring
rows carry an ``rrule``; that is why the loader writes Events directly rather
than going through the contributions queue, which drops the rrule). The two
monthly calendar IMAGES are surfaced on the ``/seniors`` page
(:data:`CALENDAR_IMAGES`), never parsed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, time, timedelta

SOURCE = "lhc_senior_center"
VENUE_NAME = "Lake Havasu Senior Center"
VENUE_ADDRESS = "450 Acoma Blvd S, Lake Havasu City, AZ 86406"
PHONE = "(928) 453-0715"
HOME_URL = "https://lakehavasuseniorcenter.com/home"
EVENTS_URL = "https://lakehavasuseniorcenter.com/current-events"

# Every senior-center occurrence carries this tag; the Seniors calendar section
# (app.events.senior_filter.is_senior_event) keys off it.
SENIOR_TAGS: tuple[str, ...] = ("senior",)

# The two MONTHLY calendar graphics shown on the /seniors page. The center's CDN
# media id changes when a new month is posted, so update these when the center
# publishes the next month (the /seniors page also links to EVENTS_URL for the
# always-current source).
CALENDAR_IMAGES: dict[str, str] = {
    "lunch_menu": (
        "https://images.leadconnectorhq.com/image/f_webp/q_80/r_1200/"
        "u_https://assets.cdn.filesafe.space/E6AiALItCKTzitYBTbln/media/"
        "6a1dc5455a3e6e89b624d03c.png"
    ),
    "activities": (
        "https://images.leadconnectorhq.com/image/f_webp/q_80/r_1200/"
        "u_https://assets.cdn.filesafe.space/E6AiALItCKTzitYBTbln/media/"
        "6a31650b1b95dbb2c225872c.png"
    ),
}


@dataclass(frozen=True)
class RecurringActivity:
    """One weekly recurring activity at the center."""

    title: str
    byday: tuple[str, ...]  # RFC 5545 weekday tokens, e.g. ("MO", "WE", "FR")
    start: time
    end: time | None
    description: str
    cost: str | None = None


# Weekday community lunch (Mohave County Senior Nutrition Program). The specific
# daily entree lives in the monthly menu IMAGE (shown on /seniors); this is the
# standing 11:15 AM lunch occurrence.
COMMUNITY_LUNCH = RecurringActivity(
    title="Community Lunch (Meals on Wheels)",
    byday=("MO", "TU", "WE", "TH", "FR"),
    start=time(11, 15),
    end=time(12, 0),
    description=(
        "Hot community lunch served weekdays 11:15 AM-12:00 PM at the Lake "
        "Havasu Senior Center (Mohave County Senior Nutrition Program). A $5 "
        "donation is suggested for guests 60 and over; $7 for guests under 60. "
        "The menu changes daily -- see the monthly lunch menu calendar."
    ),
    cost="$5 suggested (60+) / $7 (under 60)",
)

# Transcribed from the center's published Weekly Activities Calendar (rooms noted
# on the calendar as -1 / -2 / -DR are dropped here). Update if the center
# changes days/times.
RECURRING_ACTIVITIES: tuple[RecurringActivity, ...] = (
    RecurringActivity(
        title="Exercise Class",
        byday=("MO", "WE", "FR"),
        start=time(8, 30),
        end=time(9, 30),
        description=(
            "Low-impact, light-intensity exercise class for ages 50-plus at the "
            "Lake Havasu Senior Center, helping with mobility, strength and "
            "balance. Weekly on Monday, Wednesday and Friday mornings."
        ),
    ),
    RecurringActivity(
        title="Ping Pong",
        byday=("MO", "WE", "FR"),
        start=time(9, 30),
        end=None,
        description=(
            "Open ping pong / table tennis at the Lake Havasu Senior Center, "
            "weekly on Monday, Wednesday and Friday mornings."
        ),
    ),
    RecurringActivity(
        title="Hand & Foot",
        byday=("TU",),
        start=time(12, 30),
        end=None,
        description=(
            "Hand & Foot, a Canasta-style card game, at the Lake Havasu Senior "
            "Center every Tuesday afternoon. New players welcome."
        ),
    ),
    RecurringActivity(
        title="Party Bridge",
        byday=("TU", "TH"),
        start=time(12, 30),
        end=None,
        description=(
            "Weekly party bridge card game at the Lake Havasu Senior Center on "
            "Tuesday and Thursday afternoons. New players welcome."
        ),
    ),
    RecurringActivity(
        title="Laughing Yoga",
        byday=("WE",),
        start=time(12, 30),
        end=None,
        description=(
            "Laughing Yoga at the Lake Havasu Senior Center every Wednesday "
            "afternoon -- gentle movement and laughter to reduce stress and "
            "lift the mood. Fitness and fun rolled into one."
        ),
    ),
    RecurringActivity(
        title="Pinochle",
        byday=("WE", "FR"),
        start=time(12, 30),
        end=None,
        description=(
            "Weekly pinochle card game at the Lake Havasu Senior Center on "
            "Wednesday and Friday afternoons."
        ),
    ),
    RecurringActivity(
        title="Open Arts & Crafts",
        byday=("TH",),
        start=time(8, 30),
        end=time(11, 0),
        description=(
            "Open Arts and Craft Day at the Lake Havasu Senior Center, every "
            "Thursday from 8:30 to 11:00 AM. Bring a project or start something "
            "new with a friendly group."
        ),
    ),
    RecurringActivity(
        title="Music Jam",
        byday=("TH",),
        start=time(9, 0),
        end=None,
        description=(
            "The Thursday Morning Music Jam at the Lake Havasu Senior Center -- "
            "local musicians playing together every Thursday morning. Listeners "
            "and players welcome."
        ),
    ),
    RecurringActivity(
        title="Bunco",
        byday=("TH",),
        start=time(12, 30),
        end=None,
        description=(
            "Bunco -- the easy, social dice game -- at the Lake Havasu Senior "
            "Center every Thursday afternoon. No experience needed; prizes, "
            "snacks and fun."
        ),
    ),
    RecurringActivity(
        title="Qigong Tai Chi",
        byday=("FR",),
        start=time(12, 0),
        end=None,
        description=(
            "Weekly Tai Chi Qigong class at the Lake Havasu Senior Center -- "
            "gentle, low-impact movement for flexibility, balance and "
            "relaxation. Every Friday; all skill levels welcome."
        ),
        cost="$1 per class",
    ),
    RecurringActivity(
        title="Mexican Train Dominoes",
        byday=("FR",),
        start=time(12, 30),
        end=None,
        description=(
            "Weekly Mexican Train dominoes at the Lake Havasu Senior Center on "
            "Friday afternoons. A relaxed, social game; new players welcome."
        ),
    ),
    RecurringActivity(
        title="Open Billiards",
        byday=("MO", "TU", "WE", "TH", "FR"),
        start=time(8, 30),
        end=time(15, 30),
        description=(
            "Open billiards / pool table play at the Lake Havasu Senior Center "
            "during operating hours, Monday through Friday from 8:30 AM to 3:30 "
            "PM. Drop in, bring a friend or make new ones."
        ),
    ),
)


@dataclass(frozen=True)
class SpecialEvent:
    """A dated special event the center posts (often as a flyer image)."""

    title: str
    start_date: date
    end_date: date | None
    start: time | None
    end: time | None
    description: str


# Dated specials posted as FLYER IMAGES on the Current Events page (the text
# parser can't read these). Add new flyers here; past ones drop off via
# curated_special_specs(). Keep titles/dates faithful to the flyer.
CURATED_SPECIAL_EVENTS: tuple[SpecialEvent, ...] = (
    SpecialEvent(
        title="Christmas in July",
        start_date=date(2026, 7, 8),
        end_date=date(2026, 7, 10),
        start=time(9, 0),
        end=time(13, 0),
        description=(
            "Christmas in July at the Lake Havasu Senior Center -- shop a "
            "wonderful selection of holiday decor, collectibles and hidden "
            "treasures. July 8-10, 9:00 AM-1:00 PM. Every purchase makes a "
            "difference: all proceeds benefit Meals on Wheels and senior "
            "nutrition. Call (928) 453-0715."
        ),
    ),
    SpecialEvent(
        title="Celebrate Our Seniors: Ice Cream Social",
        start_date=date(2026, 8, 21),
        end_date=None,
        start=time(11, 45),
        end=None,
        description=(
            "Let's celebrate our seniors! Join us for an Ice Cream Social at the "
            "Lake Havasu Senior Center on August 21 at 11:45 AM -- ice cream, "
            "root beer floats, fun and fellowship, marking National Senior "
            "Citizens Day. RSVP (928) 453-0715."
        ),
    ),
)


@dataclass
class SeniorEventSpec:
    """One event to load into the calendar (recurring or one-off)."""

    title: str
    description: str
    date: date
    start_time: time
    end_time: time | None = None
    end_date: date | None = None
    rrule: str | None = None
    is_recurring: bool = False
    cost: str | None = None
    tags: list[str] = field(default_factory=lambda: list(SENIOR_TAGS))
    event_url: str = EVENTS_URL
    source: str = SOURCE


_BYDAY_INDEX = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
# A fixed Monday so re-runs produce a stable anchor date (idempotent rows).
_ANCHOR_BASE = date(2024, 1, 1)  # Monday


def anchor_date(byday: tuple[str, ...]) -> date:
    """A stable ``date`` that is a real occurrence weekday for ``byday``.

    The events calendar expands a recurring row from ``DTSTART = date +
    start_time`` against the rrule (see app.events.recurrence.expand_event), and
    a second pass also emits the row on its stored ``date``. Anchoring on a
    weekday the rule actually fires keeps that stored-date occurrence valid.
    """
    first = min(_BYDAY_INDEX[d] for d in byday)
    return _ANCHOR_BASE + timedelta(days=first)


def rrule_for(byday: tuple[str, ...]) -> str:
    """``FREQ=WEEKLY;BYDAY=...`` body (perpetual; no UNTIL)."""
    return "FREQ=WEEKLY;BYDAY=" + ",".join(byday)


def _activity_spec(a: RecurringActivity) -> SeniorEventSpec:
    return SeniorEventSpec(
        title=a.title,
        description=a.description,
        date=anchor_date(a.byday),
        start_time=a.start,
        end_time=a.end,
        rrule=rrule_for(a.byday),
        is_recurring=True,
        cost=a.cost,
        tags=list(SENIOR_TAGS),
    )


def recurring_specs() -> list[SeniorEventSpec]:
    """All standing weekly activities + the daily community lunch."""
    return [_activity_spec(a) for a in (COMMUNITY_LUNCH, *RECURRING_ACTIVITIES)]


def curated_special_specs(today: date | None = None) -> list[SeniorEventSpec]:
    """Curated flyer specials whose last day is today or later."""
    today = today or date.today()
    out: list[SeniorEventSpec] = []
    for e in CURATED_SPECIAL_EVENTS:
        last_day = e.end_date or e.start_date
        if last_day < today:
            continue
        out.append(
            SeniorEventSpec(
                title=e.title,
                description=e.description,
                date=e.start_date,
                end_date=e.end_date,
                start_time=e.start or time(0, 0),
                end_time=e.end,
                is_recurring=False,
                tags=list(SENIOR_TAGS),
            )
        )
    return out


_MONTH_INDEX = {
    m.lower(): i + 1
    for i, m in enumerate(
        "January February March April May June July August September October "
        "November December".split()
    )
}

_DATE_RE = re.compile(
    r"(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*,?\s+"  # optional weekday word
    r"(?P<mon>january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s+"
    r"(?P<year>\d{4})"
    r"(?:\s+(?P<t1>\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?))?"
    r"(?:\s*[-‐-―−]\s*(?P<t2>\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?))?",
    re.IGNORECASE,
)

_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?", re.IGNORECASE)

# Headings on the Current Events page that are section labels, not event titles.
_SKIP_HEADINGS = frozenset(
    {
        "upcoming events",
        "event memories",
        "we bring the fun",
        "activities & programs",
        "a community of fun",
        "join us for lunch!",
        "contact us",
        "arts & crafts",
        "wellness and fitness",
        "laughing yoga",
        "thrift store",
        "billiards, anyone?",
        "let the good times roll with bunco!",
        "about lake havasu senior center | meals on wheels",
        "lake havasu senior center | meals on wheels",
    }
)

# Titles that are really recurring activities already seeded above -- don't also
# emit them as one-off specials.
_RECURRING_TITLE_RE = re.compile(
    r"\b(tai chi|qigong|bunco|bingo|line danc|laughing yoga|"
    r"arts? (?:&|and) craft|music jam|billiards|exercise class|pinochle|"
    r"party bridge|mexican train|hand (?:&|and) foot|ping pong)\b",
    re.IGNORECASE,
)

# Headings that are a venue/address line, not an event title.
_LOCATION_RE = re.compile(
    r"\b(blvd|acoma|senior center,|\d{3,}\s+\w+\s+(?:blvd|ave|st|rd|dr))\b",
    re.IGNORECASE,
)

# Cadence/recurrence headings ("Every Friday, 12:00 PM", "Fridays") are not
# event titles and must not borrow the next block's date.
_CADENCE_RE = re.compile(
    r"^\s*(every|weekly|daily|mon|tue|wed|thu|fri|sat|sun)",
    re.IGNORECASE,
)


def _parse_time(raw: str | None) -> time | None:
    if not raw:
        return None
    m = _TIME_RE.search(raw)
    if not m:
        return None
    hour = int(m.group(1)) % 12
    minute = int(m.group(2) or 0)
    if m.group(3).lower() == "p":
        hour += 12
    try:
        return time(hour, minute)
    except ValueError:
        return None


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def parse_special_events(html: str) -> list[SeniorEventSpec]:
    """Extract TEXT-based dated one-off events from the Current Events page.

    For every heading we scan the next few headings for a full calendar date
    (``Month D, YYYY``); when one is found and the heading is a real event title
    (not a section label, a recurring activity, an address, or a cadence line),
    we emit a one-off :class:`SeniorEventSpec`. The time range is parsed when
    present, else the occurrence uses the 00:00 "time TBD" convention rather than
    a fabricated time. Returns ``[]`` on any parse failure (honest omission).
    Flyer-image specials are not text and are handled by CURATED_SPECIAL_EVENTS.
    """
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return []

    soup = BeautifulSoup(html or "", "html.parser")
    headings = soup.find_all(["h1", "h2", "h3", "h4"])
    out: list[SeniorEventSpec] = []
    seen: set[date] = set()

    for i, h in enumerate(headings):
        title = _clean(h.get_text(" "))
        if not title or len(title) < 4:
            continue
        if title.lower() in _SKIP_HEADINGS:
            continue
        if _DATE_RE.search(title):  # the heading itself is a date line
            continue
        if _RECURRING_TITLE_RE.search(title):
            continue
        if _LOCATION_RE.search(title):
            continue
        if _CADENCE_RE.match(title):
            continue

        window = " ".join(_clean(s.get_text(" ")) for s in headings[i + 1 : i + 5])
        m = _DATE_RE.search(window)
        if not m:
            continue

        month = _MONTH_INDEX.get(m.group("mon").lower())
        if not month:
            continue
        try:
            d = date(int(m.group("year")), month, int(m.group("day")))
        except ValueError:
            continue

        if d in seen:  # one special per date; first title (doc order) wins
            continue
        seen.add(d)

        start = _parse_time(m.group("t1")) or time(0, 0)
        end = _parse_time(m.group("t2"))
        out.append(
            SeniorEventSpec(
                title=title[:200],
                description=(
                    f"{title} at the Lake Havasu Senior Center "
                    f"({VENUE_ADDRESS}). See the senior center's Current Events "
                    f"page for full details, or call {PHONE}."
                ),
                date=d,
                start_time=start,
                end_time=end,
                is_recurring=False,
                tags=list(SENIOR_TAGS),
            )
        )

    return out


def fetch_events_page(timeout: float = 60.0) -> str:
    """GET the Current Events page HTML (raw). Returns '' on failure."""
    try:
        import httpx
    except Exception:
        return ""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AskHavaBot/1.0; +https://askhava.com)"
    }
    try:
        with httpx.Client(
            timeout=timeout, headers=headers, follow_redirects=True
        ) as client:
            resp = client.get(EVENTS_URL)
            resp.raise_for_status()
            return resp.text
    except Exception:
        return ""


def _dedupe(specs: list[SeniorEventSpec]) -> list[SeniorEventSpec]:
    out: list[SeniorEventSpec] = []
    seen: set[tuple[str, str, bool]] = set()
    for s in specs:
        key = (s.title.lower().strip(), s.date.isoformat(), s.is_recurring)
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def collect(html: str | None = None, *, today: date | None = None) -> list[SeniorEventSpec]:
    """All specs to load: recurring + community lunch + curated + live specials.

    ``html`` may be injected (tests / offline); when ``None`` the Current Events
    page is fetched. A failed/empty fetch still returns the recurring + lunch +
    curated specs, so the loader never produces nothing useful.
    """
    specs = recurring_specs()
    specs.extend(curated_special_specs(today=today))
    page = html if html is not None else fetch_events_page()
    specs.extend(parse_special_events(page))
    return _dedupe(specs)
