"""Split Finger Athletics — RunSwift booking platform (WS12, separate effort).

Split Finger Athletics is a youth baseball/softball + athletic-training facility
in Lake Havasu City (batting/HitTrax cages, camps, clinics, strength & agility
classes, private lessons). Its marketing site ``splitfingerathletics.com`` is a
Wix single-pager whose every "Book / Camps / Classes / Lessons" button deep-links
out to **RunSwift** (``book.runswiftapp.com/facilities/split-finger-athletics``),
where all the dated, bookable programming lives.

Discovery (2026-07-10, via a Playwright/Browser XHR capture + curl reproduction):
the Wix Bookings widget on the marketing site exposes only ONE service — an
appointment-type "Private Lesson" (no fixed date → a Program, not an event). The
camps/classes are NOT on Wix. RunSwift, however, now serves a **clean first-party
public JSON API** (the 2026-06-24 build prompt's "no capturable XHR / needs
Playwright" note is stale) — the same bookable-products-subdomain pattern as the
Altitude ROLLER connector, and pure-HTTP reproducible with just a User-Agent
(no key)::

    base    : https://book.runswiftapp.com/api/public
    facility: 760  (getFacilityBySubdomain?subdomain=split-finger-athletics)
    GET {base}/camp?facilityId=760&registrationStatus=OPEN&...   -> [camp]
    GET {base}/class?facilityId=760&registrationStatus=OPEN&...  -> [class]

Each camp/class carries its session bookings under
``service.bookingGroups[].bookings[]`` (UTC ``startTime``/``endTime``; facility
timezone ``America/Phoenix``, UTC-7 year-round, no DST). Prices are in
``prices.basePrice.cost``; ages in ``minAgeLimit``/``maxAgeLimit``.

Mapping (WS12 contract):
  * CAMP services  -> one multi-day **Event** per camp (start..end). The RunSwift
    names ("Softball Summer Session #1") carry no "camp" keyword, so the title
    gets a "— Camp" suffix — that keyword is the gate the /family/camps bucket
    filters on (``app/home/family_hub._CAMP_RE``), same trick as lhc_bmx's
    "BMX <name>".
  * CLASS services -> one **Event per session occurrence** within a bounded
    horizon. Recurring classes collapse at render time into a single
    "runs regularly" feed entry (WS5 series, ``app/events/series.py``) keyed on
    (title, location, start_time) — exactly how the gym/pool schedules render —
    so a year-round class doesn't flood the feed. The horizon caps how far ahead
    (and thus how many review-queue rows) a standing class contributes; the cron
    re-runs keep it fresh and ``find_duplicate`` stops re-flooding.
  * Private lessons / cage rentals -> NOT events (on-demand appointments /
    bookable inventory). The provider directory row + the site's own booking
    links already cover those; skipped here on purpose.

Rollout: review-queue-first (NOT auto-approved) like every WS12 connector — a
scheduled run only fills the queue for /admin approval. Each occurrence carries a
distinct RunSwift booking URL (``?campId=`` / ``?classId=&date=``) so it lands as
its own contribution, doubles as the event's Register link, and is idempotent via
the runner's find_duplicate + source-url dedup.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from app.contrib.ingest_base import EnrichedHit, RawHit
from app.events.scrapers.base import EventIngestClient, EventPayload

FACILITY_ID = 760
SUBDOMAIN = "split-finger-athletics"
API_BASE = "https://book.runswiftapp.com/api/public"
BOOKING_BASE = f"https://book.runswiftapp.com/facilities/{SUBDOMAIN}"
# Exact query strings the RunSwift SPA sends (verified pure-HTTP, 201 + JSON).
# The wide-open range params ("age=1,100" etc.) mean "no filter"; registrationStatus
# =OPEN keeps it to camps/classes still taking sign-ups.
CAMP_URL = (
    f"{API_BASE}/camp?facilityId={FACILITY_ID}&registrationStatus=OPEN"
    "&age=1,100&month=0&dayOfWeek=0&startTime=4,23&instructors=0&userId=undefined"
)
CLASS_URL = (
    f"{API_BASE}/class?facilityId={FACILITY_ID}&registrationStatus=OPEN"
    "&age=1,100&month=0&dayOfWeek=0&startTime=4,23&instructors=0"
)

VENUE_NAME = "Split Finger Athletics"
VENUE_ADDRESS = "5601 Hwy 95, Building 600, Suite F, Lake Havasu City, AZ 86404"

# America/Phoenix is UTC-7 year-round (no DST) — matches the facility.timezone.
PHOENIX = timezone(timedelta(hours=-7))

# How far ahead to emit class-session occurrences. A standing year-round class
# (e.g. Strength/Conditioning, Mon–Thu) would otherwise dump hundreds of rows into
# the review queue; this bounds each run's contribution while the render-time
# series collapse still shows it as one "runs regularly" card. Camps are discrete
# near-term dated events and use their own (wider) upcoming window.
CLASS_HORIZON_DAYS = 45
CAMP_HORIZON_DAYS = 180

_CAMP_KEYWORD_RE = re.compile(r"\b(camps?|clinics?|vbs)\b", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

_CAMP_TAGS = ("sports", "youth", "camp")
_CLASS_TAGS = ("sports", "fitness")

# Verbatim typos in the RunSwift source titles, corrected at ingest so a re-scrape
# never reintroduces them. The vendor's own class name misspells "Strength" as
# "Stength"; fixing it at the root keeps the published title (and every future
# occurrence) correct. Whole-word, on the vendor's exact spelling.
_SOURCE_TITLE_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bStength\b"), "Strength"),
)


def _clean_source_name(name: str) -> str:
    """Correct known verbatim RunSwift source-title typos (see _SOURCE_TITLE_FIXES)."""
    out = (name or "").strip()
    for pat, repl in _SOURCE_TITLE_FIXES:
        out = pat.sub(repl, out)
    return out


def _strip_html(s: str | None) -> str:
    return _WS_RE.sub(" ", _HTML_TAG_RE.sub(" ", s or "")).strip()


def _local(iso_utc: str) -> datetime:
    """Parse a RunSwift UTC ISO timestamp into facility-local (Phoenix) time."""
    return datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(PHOENIX)


def _sessions(item: dict[str, Any]) -> list[tuple[datetime, datetime]]:
    """All (start, end) session datetimes (Phoenix local) for a camp/class."""
    out: list[tuple[datetime, datetime]] = []
    for group in (item.get("service") or {}).get("bookingGroups") or []:
        for bk in group.get("bookings") or []:
            start, end = bk.get("startTime"), bk.get("endTime")
            if not start:
                continue
            try:
                s = _local(str(start))
                e = _local(str(end)) if end else s
            except (ValueError, TypeError):
                continue
            out.append((s, e))
    out.sort()
    return out


def _base_price(item: dict[str, Any]) -> float | None:
    bp = (item.get("prices") or {}).get("basePrice") or {}
    cost = bp.get("cost")
    return float(cost) if isinstance(cost, (int, float)) else None


def _ages_phrase(item: dict[str, Any]) -> str:
    """"Ages 7–12" / "Ages 11+" / "" — the '7–12' form is what /family/camps parses."""
    lo, hi = item.get("minAgeLimit"), item.get("maxAgeLimit")
    if isinstance(lo, int) and lo > 0 and isinstance(hi, int) and hi > 0:
        return f"Ages {lo}–{hi}"
    if isinstance(lo, int) and lo > 0:
        return f"Ages {lo}+"
    return ""


def _price_phrase(item: dict[str, Any], *, per_session: bool) -> str:
    price = _base_price(item)
    if price is None:
        return ""
    amount = f"{price:g}"
    return f"From ${amount} per session" if per_session else f"From ${amount}"


def _camp_title(name: str) -> str:
    """Ensure a camp/clinic keyword so the /family/camps title-gate matches."""
    name = name.strip()
    return name if _CAMP_KEYWORD_RE.search(name) else f"{name} — Camp"


def _blurb(item: dict[str, Any]) -> str:
    return _strip_html(item.get("previewText") or item.get("description"))


def _description(item: dict[str, Any], *, per_session: bool, when: str) -> str:
    parts = [
        _blurb(item),
        when,
        " · ".join(p for p in (_ages_phrase(item), _price_phrase(item, per_session=per_session)) if p),
        "Register online via Split Finger Athletics (RunSwift booking).",
    ]
    return "\n\n".join(p for p in parts if p)


class SplitFingerClient(EventIngestClient):
    source_name = "split_finger"
    scrape_source = "split_finger"

    # ---- fetch ---------------------------------------------------------------
    def _fetch_json(self, url: str) -> list[dict[str, Any]]:
        data = json.loads(self.fetch_text(url, timeout=60.0))
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        return []

    # ---- discover ------------------------------------------------------------
    def discover(self, query: dict[str, Any]) -> list[RawHit]:
        today = query.get("today")
        if not isinstance(today, date):
            today = date.today()
        hits: list[RawHit] = []
        hits.extend(self._camp_hits(self._fetch_json(CAMP_URL), today))
        hits.extend(self._class_hits(self._fetch_json(CLASS_URL), today))
        return hits

    def _camp_hits(self, camps: list[dict[str, Any]], today: date) -> list[RawHit]:
        horizon = today + timedelta(days=CAMP_HORIZON_DAYS)
        hits: list[RawHit] = []
        for camp in camps:
            if not camp.get("active", True):
                continue
            sessions = _sessions(camp)
            if not sessions:
                continue
            days = sorted({s.date() for s, _ in sessions})
            start_day, end_day = days[0], days[-1]
            # Skip fully-past or far-future camps (still-running counts as upcoming).
            if end_day < today or start_day > horizon:
                continue
            first_start, first_end = sessions[0]
            campid = camp.get("campId")
            url = f"{BOOKING_BASE}/camps?campId={campid}"
            hits.append(
                RawHit(
                    source=self.source_name,
                    source_stable_id=url,
                    name=_clean_source_name(str(camp.get("name") or "Camp")),
                    raw={
                        "kind": "camp",
                        "item": camp,
                        "start_date": start_day.isoformat(),
                        "end_date": end_day.isoformat(),
                        "start_time": first_start.strftime("%H:%M"),
                        "end_time": first_end.strftime("%H:%M"),
                        "url": url,
                    },
                )
            )
        return hits

    def _class_hits(self, classes: list[dict[str, Any]], today: date) -> list[RawHit]:
        horizon = today + timedelta(days=CLASS_HORIZON_DAYS)
        hits: list[RawHit] = []
        seen: set[str] = set()
        for cls in classes:
            if not cls.get("active", True):
                continue
            classid = cls.get("classId")
            for start, end in _sessions(cls):
                day = start.date()
                if day < today or day > horizon:
                    continue
                hhmm = start.strftime("%H%M")
                url = f"{BOOKING_BASE}/classes?classId={classid}&date={day.isoformat()}&t={hhmm}"
                if url in seen:
                    continue
                seen.add(url)
                hits.append(
                    RawHit(
                        source=self.source_name,
                        source_stable_id=url,
                        name=_clean_source_name(str(cls.get("name") or "Class")),
                        raw={
                            "kind": "class",
                            "item": cls,
                            "start_date": day.isoformat(),
                            "start_time": start.strftime("%H:%M"),
                            "end_time": end.strftime("%H:%M"),
                            "url": url,
                        },
                    )
                )
        return hits

    def enrich(self, hit: RawHit) -> EnrichedHit:
        return EnrichedHit(raw_hit=hit, enriched=dict(hit.raw))

    def dedupe_key(self, hit: RawHit) -> str:
        return hit.source_stable_id

    # ---- map -----------------------------------------------------------------
    def to_event_payload(self, hit: EnrichedHit) -> EventPayload:
        raw = hit.enriched
        item = raw["item"]
        start_date = date.fromisoformat(str(raw["start_date"]))
        start_time = time.fromisoformat(str(raw["start_time"]))
        end_time = time.fromisoformat(str(raw["end_time"])) if raw.get("end_time") else None
        url = str(raw["url"])

        if raw["kind"] == "camp":
            end_date = date.fromisoformat(str(raw["end_date"]))
            name = _camp_title(_clean_source_name(str(item.get("name") or "Camp")))
            when = _multi_day_when(start_date, end_date)
            desc = _description(item, per_session=False, when=when)
            tags = list(_CAMP_TAGS)
        else:
            end_date = None
            name = _clean_source_name(str(item.get("name") or "Class"))
            desc = _description(item, per_session=True, when="Recurring class at Split Finger Athletics.")
            tags = list(_CLASS_TAGS)

        return EventPayload(
            name=name,
            entity_type="event",
            source=self.scrape_source,
            start_date=start_date,
            end_date=end_date,
            start_time=start_time,
            end_time=end_time,
            venue_name=VENUE_NAME,
            address=VENUE_ADDRESS,
            description=desc,
            event_url=url,
            source_stable_url=url,
            category_slug="events",
            tags=tags,
        )


_MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _multi_day_when(start: date, end: date) -> str:
    """"3-day camp (Jul 13–15)." / "Camp on Jul 13." for a single-day camp."""
    if end == start:
        return f"Camp on {_MON[start.month - 1]} {start.day}."
    n = (end - start).days + 1
    if end.month == start.month:
        span = f"{_MON[start.month - 1]} {start.day}–{end.day}"
    else:
        span = f"{_MON[start.month - 1]} {start.day} – {_MON[end.month - 1]} {end.day}"
    return f"{n}-day camp ({span})."
