"""Home "Today in Lake Havasu" unified feed (Phase 2).

The home feed is the heart of the page: one scannable list for today, grouped
into four collapsed sections — **Events**, **Classes & fitness**, **Open all
day**, **At the movies**. Events open by default; the rest load collapsed, and
every row is collapsed until tapped (the template uses nested ``<details>``).

This builder is a *presentation remap* over the SAME deduped pipeline the
``/events-ui`` accordion uses (:func:`app.home.events_views.day_groups`), so the
home feed and the full calendar can never disagree on what's on or double-count
a cross-source twin:

* ``_live_events_by_day`` expands rrule/rdate occurrences and collapses
  cross-source event twins (two scrapers, one real-world event).
* ``class_occurrences_in_window`` + ``drop_event_duplicates`` add venue Schedule
  classes and drop any class occurrence that also exists as an Event row by
  ``(title, date, start_time)`` — the EVENT/CLASS de-dup the redesign calls for
  (e.g. the Senior Center "Exercise Class" printed once, not twice).

The four-group mapping (locked with Casey):

* **Classes & fitness** — instructional / registered things (yoga, the cooking
  class, wrestling, dog obedience): anything the shared tier classifier files as
  a class (:func:`app.home.events_views._group_for` → ``"classes"``).
* **Open all day** — drop-in venues with no single start time (all-day open
  play, the trampoline park, the arcade, the indoor playground).
* **Events** — every other happening (markets, swim, golf night, bowling) — a
  one-off with a real start time, or a time-unknown happening.
* **At the movies** — one row per film with per-theater showtimes in the expand.

Small audience tags (Kids / Seniors) ride on rows where the data supports it,
via the same positive matchers the calendar uses (never invented).
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any

from sqlalchemy.orm import Session

from app.events.class_occurrences import (
    class_occurrences_in_window,
    drop_event_duplicates,
)
from app.events.family_filter import is_family_event
from app.events.senior_filter import is_senior_event
from app.events.time_labels import short_time_label, time_sort_key
from app.events.title_clean import clean_event_title
from app.home.event_buckets import is_dropin_rec
from app.home.events_views import _group_for, _occurrence_expired, _row_time_label
from app.home.family_venues import open_today_rows
from app.home.sandstone import _live_events_by_day
from app.movies.queries import showtimes_for_day

# Display order + labels for the home feed groups. ``key`` is the stable CSS/JSON
# hook (data-group, the swatch class); never user-visible.
FEED_GROUP_DEFS: tuple[tuple[str, str], ...] = (
    ("events", "Events"),
    ("classes", "Classes & fitness"),
    ("open_all_day", "Open all day"),
    ("movies", "At the movies"),
)

# Rollup nouns for the "· 6 events · 7 classes · 4 movies" summary line.
_GROUP_NOUNS: dict[str, tuple[str, str]] = {
    "events": ("event", "events"),
    "classes": ("class", "classes"),
    "open_all_day": ("open all day", "open all day"),
    "movies": ("movie", "movies"),
}

# All-day drop-in titles whose 00:00/None start means "runs all day" rather than
# "time unknown" — these route to "Open all day". Mirrors
# :data:`app.home.events_views._ALL_DAY_TITLE_RE` (kept local to avoid importing a
# private name across modules).
_ALL_DAY_TITLE_RE = re.compile(r"\b(?:pickleball|open play)\b", re.IGNORECASE)


def _audience_tags(title: str | None, tags: list[str] | None) -> list[str]:
    """Kids / Seniors row tags from the same positive matchers the calendar
    uses. Empty when there is no signal — never an invented tag."""
    out: list[str] = []
    if is_family_event(title or "", tags):
        out.append("Kids")
    if is_senior_event(title or "", tags):
        out.append("Seniors")
    return out


def _happening_bucket(title: str, start_time: time | None, end_time: time | None) -> str:
    """Route a non-class happening to "events" or "open_all_day".

    A real start time → Events. No single start time AND an all-day/drop-in title
    (open play, open swim/gym) → Open all day. A genuinely time-unknown happening
    stays in Events (shown as "Time TBD") rather than masquerading as all-day.
    """
    if short_time_label(start_time, end_time) is not None:
        return "events"
    if is_dropin_rec(title) or _ALL_DAY_TITLE_RE.search(title or ""):
        return "open_all_day"
    return "events"


def _summary(counts: dict[str, int]) -> str:
    """"6 events · 7 classes · 4 movies" — zero/empty groups omitted."""
    bits: list[str] = []
    for key, _label in FEED_GROUP_DEFS:
        n = counts.get(key, 0)
        if not n:
            continue
        singular, plural = _GROUP_NOUNS[key]
        bits.append(f"{n} {singular if n == 1 else plural}")
    return " · ".join(bits)


def _movie_films(db: Session, *, day: date) -> list[dict[str, Any]]:
    """One row per film for the "At the movies" group, per-theater showtimes in
    the expand. A film at two theaters collapses to a single row; the summary
    reads "2 theaters · next 12:40 PM" (or "Star Cinemas · next 10:00 AM")."""
    films: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for tg in showtimes_for_day(db, day=day):
        for fc in tg.films:
            first = fc.showtimes[0]
            f = films.get(fc.title)
            if f is None:
                f = {
                    "title": fc.title,
                    "tags": _audience_tags(fc.title, None),
                    "theaters": [],
                    "_sort": first.sort,
                    "next_label": first.label,
                    "url": first.url,
                }
                films[fc.title] = f
                order.append(fc.title)
            f["theaters"].append(
                {"name": tg.name, "times": [s.label for s in fc.showtimes]}
            )
            if first.sort < f["_sort"]:
                f["_sort"] = first.sort
                f["next_label"] = first.label
                f["url"] = first.url

    out: list[dict[str, Any]] = []
    for title in order:
        f = films[title]
        n = len(f["theaters"])
        venue = f"{n} theaters" if n > 1 else f["theaters"][0]["name"]
        f["summary"] = f"{venue} · next {f['next_label']}"
        out.append(f)
    out.sort(key=lambda f: f["_sort"])
    return out


def _event_feed_row(
    *,
    title: str,
    venue: str | None,
    url: str | None,
    start_time: time | None,
    end_time: time | None,
    recurring: bool,
    tags: list[str] | None,
) -> dict[str, Any]:
    return {
        "sort": time_sort_key(start_time, end_time),
        "time_label": _row_time_label(title or "", start_time, end_time),
        "title": clean_event_title(title, location_name=venue),
        "venue": venue,
        "url": url,
        "recurring": recurring,
        "tags": tags if tags is not None else _audience_tags(title, None),
    }


def today_feed(
    db: Session, *, day: date, now: datetime | None = None
) -> dict[str, Any]:
    """Build the home four-group feed for ``day``.

    Returns ``{"groups": [...], "counts": {...}, "summary": str}``. Empty groups
    are omitted entirely (honest omission — never a labeled empty shell). The
    Events group opens by default; if the day has no events, the first present
    group opens so the feed never loads fully collapsed.
    """
    events = _live_events_by_day(db, window_start=day, window_end=day).get(day, [])
    # On the current day, drop occurrences that finished >1h ago (no-op for
    # past/future days or when ``now`` isn't supplied) — same rule as day_groups.
    events = [
        ev
        for ev in events
        if not _occurrence_expired(day, ev.start_time, ev.end_time, now)
    ]
    event_keys = {
        ((ev.title or "").strip().lower(), day, ev.start_time) for ev in events
    }

    buckets: dict[str, list[dict[str, Any]]] = {
        "events": [],
        "classes": [],
        "open_all_day": [],
    }

    def _bucket_for(title: str, tags: list[str] | None, featured: bool, recurring: bool,
                    start: time | None, end: time | None) -> str:
        primary = _group_for(title=title, tags=tags, featured=featured, recurring=recurring)
        if primary == "classes":
            return "classes"
        return _happening_bucket(title, start, end)

    for ev in events:
        bkey = _bucket_for(
            ev.title or "", ev.tags, bool(ev.featured), bool(ev.is_recurring),
            ev.start_time, ev.end_time,
        )
        buckets[bkey].append(
            _event_feed_row(
                title=ev.title or "",
                venue=ev.location_name,
                url=f"/events/{ev.id}",
                start_time=ev.start_time,
                end_time=ev.end_time,
                recurring=bool(ev.is_recurring),
                tags=_audience_tags(ev.title or "", ev.tags),
            )
        )

    for occ in drop_event_duplicates(
        class_occurrences_in_window(db, window_start=day, window_end=day), event_keys
    ):
        if _occurrence_expired(day, occ.start_time, occ.end_time, now):
            continue
        bkey = _bucket_for(occ.title, None, False, True, occ.start_time, occ.end_time)
        buckets[bkey].append(
            _event_feed_row(
                title=occ.title,
                venue=occ.venue,
                url=occ.url,  # venue page — class series have no permalink
                start_time=occ.start_time,
                end_time=occ.end_time,
                recurring=True,
                tags=_audience_tags(occ.title, None),
            )
        )

    # Drop-in venue hours (trampoline, arcade, indoor playground, dojo/gym class
    # blocks) — always "open all day" drop-ins, never a scheduled event row.
    for vrow in open_today_rows(day):
        buckets["open_all_day"].append(
            {
                "sort": vrow["sort"],
                "time_label": vrow["time_label"],
                "title": vrow["title"],
                "venue": vrow["venue"],
                "url": vrow["url"],
                "recurring": False,
                "tags": _audience_tags(vrow["title"], None),
            }
        )

    counts: dict[str, int] = {}
    groups: list[dict[str, Any]] = []
    for key, label in FEED_GROUP_DEFS:
        if key == "movies":
            continue
        rows = sorted(buckets[key], key=lambda r: r["sort"])
        counts[key] = len(rows)
        if rows:
            groups.append({"key": key, "label": label, "count": len(rows), "rows": rows})

    films = _movie_films(db, day=day)
    counts["movies"] = len(films)
    if films:
        groups.append(
            {"key": "movies", "label": "At the movies", "count": len(films), "films": films}
        )

    has_events = any(g["key"] == "events" for g in groups)
    for i, g in enumerate(groups):
        g["open"] = (g["key"] == "events") if has_events else (i == 0)

    return {"groups": groups, "counts": counts, "summary": _summary(counts)}
