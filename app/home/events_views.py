"""View builders for the /events-ui page (Today / Week / Month redesign).

One concept at three zoom levels — "show the general category and how many,
click to see more":

* **Today / day detail** — a category accordion for a single lake-local date.
  Groups, in owner-approved order: Events (one-off, non-class), Music &
  nightlife, On the water, Fitness & classes (recurring Event rows + venue
  Schedule classes). Empty groups are omitted; the Events group opens by
  default ("most people will be looking for events").
* **Week** — 7 rows starting today: weekday + date, the top one-off headline
  (ranked via the shared :func:`app.home.sandstone._event_tier`; never a
  recurring class), and an honest per-group rollup ("2 events · 1 music ·
  14 classes"). Each row links to ``/events-ui?date=``.
* **Month** — the route reuses :func:`app.home.sandstone.calendar_month`
  (Sunday-anchored grid, one-off ``count`` + ``class_count`` per cell), so the
  events month grid and the home calendar can never disagree on alignment.

Everything rides on the existing pipeline: ``_live_events_by_day`` (rrule
expansion + cross-source dedup), ``class_occurrences_in_window`` +
``drop_event_duplicates`` (venue Schedule classes, aquatic twins dropped), and
the shared time-label contract (unknown times read "Time TBD" and sort last).
Kept out of ``router.py`` so the route stays a thin assembler and these
builders are unit-testable; the route computes ``now_lake_havasu()`` itself
(the freshness tests monkeypatch it there) and passes dates down.
"""

from __future__ import annotations

from datetime import date, time, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Event
from app.events.class_occurrences import (
    class_occurrences_in_window,
    drop_event_duplicates,
)
from app.events.family_filter import is_family_event
from app.events.time_labels import TIME_TBD_LABEL, short_time_label, time_sort_key
from app.events.title_clean import clean_event_title
from app.home.sandstone import (
    _TIER_CLASS,
    _TIER_MUSIC,
    _TIER_WATER,
    _event_tier,
    _live_events_by_day,
)

# Accordion groups in the owner-approved order: (key, label, icon).
GROUP_DEFS: tuple[tuple[str, str, str], ...] = (
    # "Around town": the catch-all one-off group needed a real name — the page
    # rendered a generic "Events 4" section next to named siblings (audit
    # events #6). Key stays "events" (rollup nouns + CSS hooks unchanged).
    ("events", "Around town", "\U0001F39F️"),
    ("music", "Music & nightlife", "\U0001F3B6"),
    ("water", "On the water", "⛵"),
    ("classes", "Fitness & classes", "\U0001F3C3"),
)

# Rollup nouns per group: (singular, plural). "music" and "on the water" read
# naturally uncounted-noun style ("1 music", "3 on the water").
_GROUP_NOUNS: dict[str, tuple[str, str]] = {
    "events": ("event", "events"),
    "music": ("music", "music"),
    "water": ("on the water", "on the water"),
    "classes": ("class", "classes"),
}


def _group_for(*, title: str, tags: list[str] | None, featured: bool, recurring: bool) -> str:
    """Map an event to its accordion group via the shared tier heuristic.

    Recurring rows and class-tier one-offs (a "Yoga Workshop") always land in
    Fitness & classes — a class never appears in the Events group. The
    remaining one-off tiers split into music / water / everything-else
    ("Events": special, community, other).
    """
    tier = _event_tier(title=title, tags=tags, featured=featured, recurring=recurring)
    return _group_for_tier(tier, recurring=recurring)


def _group_for_tier(tier: int, *, recurring: bool) -> str:
    if recurring or tier == _TIER_CLASS:
        return "classes"
    if tier == _TIER_MUSIC:
        return "music"
    if tier == _TIER_WATER:
        return "water"
    return "events"


def _event_row(ev: Event) -> dict[str, Any]:
    return {
        "sort": time_sort_key(ev.start_time, ev.end_time),
        "time_label": short_time_label(ev.start_time, ev.end_time) or TIME_TBD_LABEL,
        "title": clean_event_title(ev.title, location_name=ev.location_name),
        "venue": ev.location_name,
        "url": f"/events/{ev.id}",
        "recurring": bool(ev.is_recurring),
    }


def day_groups(db: Session, *, day: date, family: bool = False) -> list[dict[str, Any]]:
    """Category-accordion groups for one date. Empty groups are omitted.

    Rows inside each group sort chronologically with time-TBD rows last (the
    shared :func:`time_sort_key` contract). Venue Schedule classes join the
    Fitness & classes group, linking to their venue page; classes that also
    exist as Event rows are dropped by (title, date) so nothing shows twice.

    ``family=True`` (the ``?family=1`` toggle) keeps only occurrences that
    positively read as kid/family things (:func:`is_family_event`) — e.g. the
    Aquatic Center contributes Open Swim but not the adult exercise classes.
    """
    events = _live_events_by_day(db, window_start=day, window_end=day).get(day, [])
    if family:
        events = [ev for ev in events if is_family_event(ev.title, ev.tags)]
    # (title, date, start_time) triples: the start-time window keeps distinct
    # sessions apart while still suppressing renamed twins (see
    # drop_event_duplicates).
    event_keys = {((ev.title or "").strip().lower(), day, ev.start_time) for ev in events}

    rows_by_group: dict[str, list[dict[str, Any]]] = {key: [] for key, _l, _i in GROUP_DEFS}
    for ev in events:
        gkey = _group_for(
            title=ev.title or "",
            tags=ev.tags,
            featured=bool(ev.featured),
            recurring=bool(ev.is_recurring),
        )
        rows_by_group[gkey].append(_event_row(ev))

    for occ in drop_event_duplicates(
        class_occurrences_in_window(db, window_start=day, window_end=day), event_keys
    ):
        if family and not is_family_event(occ.title):
            continue
        rows_by_group["classes"].append(
            {
                "sort": time_sort_key(occ.start_time, occ.end_time),
                "time_label": short_time_label(occ.start_time, occ.end_time) or TIME_TBD_LABEL,
                "title": clean_event_title(occ.title, location_name=occ.venue),
                "venue": occ.venue,
                "url": occ.url,  # venue page — class series have no permalink
                "recurring": True,
            }
        )

    groups: list[dict[str, Any]] = []
    for key, label, icon in GROUP_DEFS:
        rows = sorted(rows_by_group[key], key=lambda r: r["sort"])
        if not rows:
            continue  # omitted entirely — never an empty labeled shell
        groups.append(
            {"key": key, "label": label, "icon": icon, "count": len(rows), "rows": rows}
        )
    # "Events" opens by default; if the date has no one-off events, open the
    # first group present so the page never loads fully collapsed.
    has_events_group = any(g["key"] == "events" for g in groups)
    for i, g in enumerate(groups):
        g["open"] = (g["key"] == "events") if has_events_group else (i == 0)
    return groups


def rollup_summary(counts: dict[str, int]) -> str:
    """Honest per-group rollup line ("2 events · 1 music · 14 classes").

    Zero-count groups are omitted; an empty day returns "" (the template
    renders its own empty copy, never a fabricated count).
    """
    bits: list[str] = []
    for key, _label, _icon in GROUP_DEFS:
        n = counts.get(key, 0)
        if not n:
            continue
        singular, plural = _GROUP_NOUNS[key]
        bits.append(f"{n} {singular if n == 1 else plural}")
    return " · ".join(bits)


def week_rows(
    db: Session, *, start: date, days: int = 7, family: bool = False
) -> list[dict[str, Any]]:
    """The next-``days`` rows for the week view (gap-free: contiguous dates).

    Every live event occurrence in the window is counted in exactly one day's
    rollup. The headline is the day's top ONE-OFF by ``(_event_tier, time)`` —
    a recurring class can never take it; days with no one-offs headline
    nothing and show only the rollup (or honest empty copy).

    ``family=True`` applies the same kid/family occurrence filter as
    :func:`day_groups`, so the week rollups agree with the day view.
    """
    end = start + timedelta(days=days - 1)
    by_day = _live_events_by_day(db, window_start=start, window_end=end)
    if family:
        by_day = {
            d: [ev for ev in evs if is_family_event(ev.title, ev.tags)]
            for d, evs in by_day.items()
        }
    event_keys = {
        ((ev.title or "").strip().lower(), d, ev.start_time)
        for d, evs in by_day.items()
        for ev in evs
    }
    sched_by_day: dict[date, int] = {}
    for occ in drop_event_duplicates(
        class_occurrences_in_window(db, window_start=start, window_end=end), event_keys
    ):
        if family and not is_family_event(occ.title):
            continue
        sched_by_day[occ.date] = sched_by_day.get(occ.date, 0) + 1

    rows: list[dict[str, Any]] = []
    for i in range(days):
        d = start + timedelta(days=i)
        counts = {key: 0 for key, _l, _i in GROUP_DEFS}
        counts["classes"] = sched_by_day.get(d, 0)
        headline: dict[str, Any] | None = None
        best_key: tuple[int, int, time] | None = None
        for ev in by_day.get(d, []):
            tier = _event_tier(
                title=ev.title or "",
                tags=ev.tags,
                featured=bool(ev.featured),
                recurring=bool(ev.is_recurring),
            )
            counts[_group_for_tier(tier, recurring=bool(ev.is_recurring))] += 1
            if ev.is_recurring:
                continue  # a recurring class never headlines
            rank: tuple[int, int, time] = (tier, *time_sort_key(ev.start_time, ev.end_time))
            if best_key is None or rank < best_key:
                best_key = rank
                headline = {
                    "title": clean_event_title(ev.title, location_name=ev.location_name),
                    "time": short_time_label(ev.start_time, ev.end_time),
                }
        rows.append(
            {
                "iso": d.isoformat(),
                "label": "Today" if i == 0 else d.strftime("%a"),
                "daynum": d.day,
                "is_today": i == 0,
                "headline": headline,
                "counts": counts,
                "summary": rollup_summary(counts),
                "total": sum(counts.values()),
            }
        )
    return rows
