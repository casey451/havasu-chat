"""WS10 /family hub + /family/camps view-models.

Presentation-only glue over EXISTING data (no new sources, no fabrication):

* :func:`kids_today_rows` — today's kid/family events, from the SAME
  ``day_groups(family=True)`` narrow the ``?family=1`` calendar toggle uses.
* :func:`camps_index` — a seasonal index of day camps / clinics / VBS already in
  the events DB (title-keyword selected, deduped, with a date-range label), built
  so a WS12 connector's camp rows slot in with no page change.
* :func:`family_tiles` — the hub's subcategory tiles, each linking to a real
  ``/categories/...`` list (verified against app.categories.cross_surface — they
  respect the thin-page gate, so none 404), never a ``/chat?q=`` deflection.

The "beat the heat / open today for kids" list is the curated
``app.home.family_venues.open_today_rows`` (indoor play, trampoline, arcade,
bowling) rendered straight in the route — real venue hours, honest-omit.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Event
from app.events.time_labels import format_short_time, is_time_tbd
from app.home import events_views

# Hub hero copy (single-sourced here so the route doesn't depend on the retired
# mode-landing config). The heading is load-bearing for test_mode_landings.
FAMILY_HERO: dict[str, str] = {
    "eyebrow": "Family",
    "heading": "Plenty to do with the kids",
    "blurb": (
        "Today's kid-friendly events, where to beat the heat indoors, summer "
        "camps, and the parks — the answer to “there's nothing to do here.”"
    ),
}

_MON = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

# A camp/clinic/VBS in the title. Word-boundary matched so "campus" / "campaign"
# / "campground" don't read as camps. The DB prefilter (a LIKE on the same stems)
# narrows the scan; this is the precise gate.
_CAMP_RE = re.compile(r"\b(camps?|clinics?|vbs)\b|vacation bible", re.IGNORECASE)

# Adult-audience veto (Casey 2026-07-08 live review): a KIDS camps page must not
# list adult programming (e.g. P&R's "Adult Intro to Watersports"). Excluded when
# the title leads with "Adult"/"Adults" OR the row carries an adult audience tag
# (the parks_rec loader stamps ``adult`` from an "adult" keyword — AUDIENCE_KEYWORDS).
_ADULT_TITLE_RE = re.compile(r"^\s*adults?\b", re.IGNORECASE)
_ADULT_TAGS = frozenset({"adult", "adults"})


def _walk_rows(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten every event row across a day_groups tree (rows + subgroups)."""
    out: list[dict[str, Any]] = []

    def _walk(node: dict[str, Any]) -> None:
        out.extend(node.get("rows") or [])
        for sub in node.get("subgroups") or []:
            _walk(sub)
        for child in node.get("children") or []:
            _walk(child)

    for g in groups:
        _walk(g)
    return out


def kids_today_rows(
    db: Session, *, day: date, now: datetime | None = None, limit: int = 12
) -> list[dict[str, str]]:
    """Today's kid/family EVENTS — the same ``family=True`` narrow the ``?family=1``
    calendar toggle uses. Each row is ``{title, time_label, venue, url}``.

    Kept to real dated events (an internal ``/events/<id>`` link), so the feed is
    the day's kid *happenings* — the recurring youth-class roster and venue-hours
    rows are excluded here (venues show in the separate "open today" list). Deduped
    by URL: a day_groups node exposes its rows both flat and split into subgroups,
    so we collapse the two. Honest-omit → ``[]``.
    """
    groups = events_views.day_groups(db, day=day, family=True, now=now)
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for r in _walk_rows(groups):
        url = (r.get("url") or "").strip()
        title = (r.get("title") or "").strip()
        # Real dated events only (internal permalink); drops class rosters + hours.
        if not title or not url.startswith("/events/") or url in seen:
            continue
        seen.add(url)
        tl = (r.get("time_label") or "").strip()
        out.append(
            {
                "title": title,
                "time_label": "" if "TBD" in tl.upper() else tl,
                "venue": (r.get("venue") or "").strip(),
                "url": url,
            }
        )
    return out[:limit]


# Inline camps-card detail (Casey 2026-07-10): time · ages · price · Register,
# each shown only when the data is really present (graceful omission — no empty
# separators). Age + price come from the connector's own description text
# (structured Event columns don't carry them); a camp without them just omits.
_AGES_RE = re.compile(r"\bages?\s*(\d{1,2})\s*(?:[–-]|to)\s*(\d{1,2})\b", re.IGNORECASE)
_PRICE_RE = re.compile(r"\bfrom\s*\$\s*(\d{1,4}(?:\.\d{2})?)\b", re.IGNORECASE)


def _time_range_label(start: time | None, end: time | None) -> str:
    """"9 AM–4 PM" / "10 AM" / "" — never a fabricated midnight."""
    if is_time_tbd(start, end) or start is None:
        return ""
    lo = format_short_time(start)
    if end and end != start:
        return f"{lo}–{format_short_time(end)}"
    return lo


def _ages_label(description: str | None) -> str:
    m = _AGES_RE.search(description or "")
    return f"Ages {m.group(1)}–{m.group(2)}" if m else ""


def _price_label(description: str | None) -> str:
    m = _PRICE_RE.search(description or "")
    return f"From ${m.group(1)}" if m else ""


def _register_url(ev: Event) -> str:
    """The external booking/registration link (the connector's source_ref), or ""."""
    for u in (ev.source_url, ev.event_url):
        s = (u or "").strip()
        if s.startswith("http") and "askhava.com" not in s:
            return s
    return ""


def _date_range_label(start: date, end: date | None, *, recurring: bool) -> str:
    """"Jul 6", "Jul 6–10", "Jul 28 – Aug 2", or "Jul 6 onward" for a series."""
    s = f"{_MON[start.month - 1]} {start.day}"
    if end and end != start:
        if end.month == start.month:
            return f"{s}–{end.day}"
        return f"{s} – {_MON[end.month - 1]} {end.day}"
    if recurring:
        return f"{s} onward"
    return s


def camps_index(
    db: Session, *, today: date, window_days: int = 120, limit: int = 60
) -> list[dict[str, str]]:
    """Upcoming day camps / clinics / VBS from the events DB, one card per camp.

    Selected by a camp/clinic/VBS keyword in the title (the clearest seasonal-
    program signal). Same-title occurrences on consecutive days collapse into ONE
    card with a date-range label ("Jul 13–17") — so a booking-platform camp that
    lands as five single-day rows reads as one week, matching the WS5 series /
    Rainforest Rush presentation (a separate later week is its own card). Each
    carries the range label + venue + internal ``/events/<id>`` link (which holds
    the external "Register" button, WS5 M7). Empty list → the page shows an honest
    "nothing scheduled yet" state, never a fabricated camp. A WS12 connector's
    camp rows appear here for free.
    """
    horizon = today + timedelta(days=window_days)
    stmt = (
        select(Event)
        .where(
            Event.status == "live",
            # cheap DB prefilter on the stems; _CAMP_RE is the precise gate below
            or_(
                Event.normalized_title.contains("camp"),
                Event.normalized_title.contains("clinic"),
                Event.normalized_title.contains("vbs"),
                Event.normalized_title.contains("vacation bible"),
            ),
            # upcoming or still running, and starting within the window
            or_(Event.date >= today, Event.end_date >= today),
            Event.date <= horizon,
        )
        .order_by(Event.date, Event.start_time)
    )
    rows = db.execute(stmt).scalars().all()
    # Group eligible events by title (rows already date-sorted), then split each
    # title into consecutive-day runs so five single-day camp rows read as one
    # "Jul 13–17" week while a distinct later week stays a separate card.
    by_title: dict[str, list[Event]] = {}
    for ev in rows:
        title = (ev.title or "").strip()
        if not title or not _CAMP_RE.search(title):
            continue
        # Never surface adult programming on the kids camps page.
        if _ADULT_TITLE_RE.match(title):
            continue
        if {str(t).strip().lower() for t in (ev.tags or [])} & _ADULT_TAGS:
            continue
        by_title.setdefault((ev.normalized_title or title).strip().casefold(), []).append(ev)

    cards: list[tuple[date, dict[str, str]]] = []
    for events in by_title.values():
        for run in _consecutive_runs(events):
            first = run[0]
            run_start = first.date
            run_end = max((e.end_date or e.date) for e in run)
            cards.append(
                (
                    run_start,
                    {
                        "title": (first.title or "").strip(),
                        "when": _date_range_label(
                            run_start, run_end, recurring=any(e.is_recurring for e in run)
                        ),
                        "venue": (first.location_name or "").strip(),
                        "url": f"/events/{first.id}",
                        # Inline detail — each empty-string when the data is absent.
                        "time": _time_range_label(first.start_time, first.end_time),
                        "ages": _ages_label(first.description),
                        "price": _price_label(first.description),
                        "register_url": _register_url(first),
                    },
                )
            )
    cards.sort(key=lambda c: c[0])
    return [card for _, card in cards[:limit]]


def _consecutive_runs(events: list[Event]) -> list[list[Event]]:
    """Split date-sorted same-title events into runs of consecutive days.

    A new run starts when the gap from the previous occurrence's end exceeds one
    day (so Mon–Fri stays one run, but the next week — Fri→Mon is a 3-day gap —
    is its own run). A multi-day event is a run of one.
    """
    ordered = sorted(events, key=lambda e: (e.date, e.start_time or time.min))
    runs: list[list[Event]] = []
    cur: list[Event] = []
    for ev in ordered:
        if cur and ev.date <= (cur[-1].end_date or cur[-1].date) + timedelta(days=1):
            cur.append(ev)
        else:
            if cur:
                runs.append(cur)
            cur = [ev]
    if cur:
        runs.append(cur)
    return runs


# The hub's subcategory tiles → real filtered leaf / department lists (verified in
# app.categories.cross_surface; they respect the thin-page gate, so none 404).
# Link-only, no counts (a tile can't disagree with the leaf's own number — WS7).
_FAMILY_TILES: tuple[tuple[str, str, str], ...] = (
    ("Summer camps & clinics", "Day camps, sports clinics, VBS", "/family/camps"),
    ("Classes & lessons", "Dance, martial arts, gymnastics", "/categories/family-and-education"),
    (
        "Parks & playgrounds",
        "Shade, splash pads, beaches",
        "/categories/things-to-do-and-attractions/parks-and-playgrounds",
    ),
    (
        "Indoor fun & arcades",
        "Beat the heat inside",
        "/categories/things-to-do-and-attractions/family-fun-and-arcades",
    ),
)


def family_tiles() -> list[dict[str, str]]:
    """The /family subcategory tiles (label + blurb + real URL)."""
    return [{"label": lbl, "blurb": blurb, "url": url} for lbl, blurb, url in _FAMILY_TILES]
