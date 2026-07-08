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
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Event
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
    program signal), deduped by title (keeping the earliest occurrence), and
    limited to the summer-ahead window. Each carries a date-range label + venue +
    internal ``/events/<id>`` link (which holds the external "Register" button,
    WS5 M7). Empty list → the page shows an honest "nothing scheduled yet" state,
    never a fabricated camp. A WS12 connector's camp rows appear here for free.
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
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for ev in rows:
        title = (ev.title or "").strip()
        if not title or not _CAMP_RE.search(title):
            continue
        key = (ev.normalized_title or title).strip().casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "title": title,
                "when": _date_range_label(ev.date, ev.end_date, recurring=bool(ev.is_recurring)),
                "venue": (ev.location_name or "").strip(),
                "url": f"/events/{ev.id}",
            }
        )
        if len(out) >= limit:
            break
    return out


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
