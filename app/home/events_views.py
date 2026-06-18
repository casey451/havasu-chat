"""View builders for the /events-ui page (Today / Week / Month redesign).

One concept at three zoom levels — "show the general category and how many,
click to see more":

* **Today / day detail** — a category accordion for a single lake-local date.
  Groups, in owner-approved order: Around town (one-off, non-class), Kids &
  Family (every kid/family occurrence PLUS "what's open for kids today" venue
  hours — see app.home.family_venues), Music & nightlife, On the water (the
  LAKE only), Aquatic Center (pool: open swim, swim lessons, aqua classes),
  Fitness & classes (recurring Event rows + venue Schedule classes). Kids &
  Family and Aquatic Center are cross-cutting overlays (see _group_for_tier):
  a kid/pool occurrence leaves its activity group for these. Empty groups are
  omitted; the Around town group opens by default.
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

import re
from datetime import date, datetime, time, timedelta
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
from app.home.event_buckets import GROUP_DEFS, GROUP_NOUNS, group_for_tier
from app.home.family_venues import open_today_rows
from app.home.sandstone import (
    _event_tier,
    _live_events_by_day,
    event_recurrence_label,
)

# Private aliases for the shared bucket definitions (the canonical names live in
# app.home.event_buckets — Slice C). Plain assignment instead of ``import ... as``
# keeps ruff's isort happy under the project's combine-as-imports=false default.
_GROUP_NOUNS = GROUP_NOUNS
_group_for_tier = group_for_tier

# GROUP_DEFS (the bucket set), _GROUP_NOUNS (rollup nouns), and _group_for_tier
# (the tier->bucket mapping) now live in :mod:`app.home.event_buckets` — the one
# definition the home week-strip also consumes (Slice C), so the two surfaces'
# legends, colors, and rollup nouns can never drift again.


def _group_for(*, title: str, tags: list[str] | None, featured: bool, recurring: bool) -> str:
    """Map an event to its accordion group via the shared tier heuristic.

    Kid/family occurrences collect in "Kids & Family"; pool activities in
    "Aquatic Center"; recurring rows and class-tier one-offs in "Fitness &
    classes". The remaining one-off tiers split into music / on-the-water /
    everything-else ("Around town": special, community, other).
    """
    tier = _event_tier(title=title, tags=tags, featured=featured, recurring=recurring)
    return _group_for_tier(tier, recurring=recurring, title=title, tags=tags)


# Phase 3 (Item 6): split the "Fitness & classes" wall into type subsections so
# a 20-30-class day is scannable. Title-keyword classifier, word-boundary matched
# in specificity order; unmatched land in the honest "Other classes" bucket.
_CLASS_SUBGROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Yoga", ("yoga", "vinyasa")),
    ("Pilates", ("pilates", "reformer", "barre")),
    ("Martial Arts", (
        "martial", "karate", "jiu jitsu", "jiu-jitsu", "bjj", "taekwondo",
        "judo", "mma", "kickbox", "muay thai", "no-gi", "no gi", "kali",
        "combat", "self defense", "self-defense", "boxing", "dojo",
    )),
    ("Dance", ("dance", "ballet", "tap", "jazz", "hip hop", "hip-hop", "ballroom")),
    ("Gymnastics", ("gymnastics", "tumbling", "tumbler", "tumble", "cheer", "ninja", "trampoline")),
    ("Strength & Cardio", (
        "strength", "weight", "crossfit", "cross fit", "bootcamp", "boot camp",
        "hiit", "cardio", "spin", "cycling", "zumba", "aerobic", "conditioning",
        "sculpt", "circuit",
    )),
)
_CLASS_SUBGROUP_ORDER: tuple[str, ...] = (
    "Yoga", "Pilates", "Strength & Cardio", "Dance", "Gymnastics",
    "Martial Arts", "Other classes",
)
_CLASS_FALLBACK_LABEL = "Other classes"
# Below this many class rows a day reads fine flat; at/above it we sub-group.
_CLASS_SUBGROUP_MIN = 6


def _class_subgroup(title: str) -> str:
    """Map a fitness/class occurrence to a type subsection by title keyword."""
    low = title.lower()
    for label, hints in _CLASS_SUBGROUPS:
        for h in hints:
            if re.search(r"\b" + re.escape(h) + r"(?:e?s|ing)?\b", low):
                return label
    return _CLASS_FALLBACK_LABEL


def _split_class_subgroups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Partition already-sorted Fitness & classes rows into ordered type
    subsections, omitting empty ones (honest-omission). Row order preserved."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(_class_subgroup(row.get("title") or ""), []).append(row)
    out: list[dict[str, Any]] = []
    for label in _CLASS_SUBGROUP_ORDER:
        sub_rows = buckets.get(label)
        if sub_rows:
            out.append({"label": label, "rows": sub_rows, "count": len(sub_rows)})
    return out


# Phase 3 (Item 6): nest the Kids & Family group by youth activity type, with
# per-day counts, and collapse the always-open drop-in venues into one section.
_FAMILY_SUBGROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Swim Lessons", ("swim",)),
    ("Youth Gymnastics", ("gymnastics", "tumbling", "tumbler", "tumble", "cheer", "ninja")),
    ("Youth Martial Arts", (
        "martial", "jiu jitsu", "jiu-jitsu", "no-gi", "no gi", "bjj", "karate",
        "taekwondo", "judo", "mma", "kickbox", "combat", "tiger", "dojo", "kali",
    )),
    ("Youth Dance", ("dance", "ballet", "tap", "jazz")),
    ("Youth Racing", ("bmx", "race", "racing", "motocross", "pump track")),
)
_FAMILY_SUBGROUP_ORDER: tuple[str, ...] = (
    "Swim Lessons", "Youth Gymnastics", "Youth Martial Arts", "Youth Dance",
    "Youth Racing", "More for kids", "Open today for kids",
)
_FAMILY_FALLBACK_LABEL = "More for kids"
_FAMILY_OPEN_LABEL = "Open today for kids"
_FAMILY_SUBGROUP_MIN = 5


def _family_subgroup(title: str) -> str:
    """Map a Kids & Family occurrence to a youth-activity subsection by title."""
    low = title.lower()
    for label, hints in _FAMILY_SUBGROUPS:
        for h in hints:
            if re.search(r"\b" + re.escape(h) + r"(?:e?s|ing)?\b", low):
                return label
    return _FAMILY_FALLBACK_LABEL


def _split_family_subgroups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Partition Kids & Family rows: scheduled occurrences by youth type, with
    the always-open drop-in venues collapsed under one "Open today for kids"
    section (ordered last). Empty subsections omitted; row order preserved."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("ongoing"):
            label = _FAMILY_OPEN_LABEL
        else:
            label = _family_subgroup(row.get("title") or "")
        buckets.setdefault(label, []).append(row)
    out: list[dict[str, Any]] = []
    for label in _FAMILY_SUBGROUP_ORDER:
        sub_rows = buckets.get(label)
        if sub_rows:
            out.append({"label": label, "rows": sub_rows, "count": len(sub_rows)})
    return out


def _event_row(ev: Event) -> dict[str, Any]:
    return {
        "sort": time_sort_key(ev.start_time, ev.end_time),
        "time_label": short_time_label(ev.start_time, ev.end_time) or TIME_TBD_LABEL,
        "title": clean_event_title(ev.title, location_name=ev.location_name),
        "venue": ev.location_name,
        "url": f"/events/{ev.id}",
        "recurring": bool(ev.is_recurring),
    }


def _occurrence_expired(
    day: date,
    start_time: time | None,
    end_time: time | None,
    now: datetime | None,
    *,
    grace_minutes: int = 60,
    default_minutes: int = 120,
) -> bool:
    """True if an occurrence on ``day`` ended more than ``grace_minutes`` ago.

    No-op (returns False) unless ``now`` is given and ``day`` is the current day,
    so the filter only ever trims *today's* finished items. Time-TBD occurrences
    (no ``start_time``) never expire. End is ``end_time`` when set, else
    ``start_time`` + ``default_minutes`` (Item 6 auto-expiry).
    """
    if now is None or start_time is None or now.date() != day:
        return False
    if end_time is not None:
        end_dt = datetime.combine(day, end_time)
    else:
        end_dt = datetime.combine(day, start_time) + timedelta(minutes=default_minutes)
    return now.replace(tzinfo=None) > end_dt + timedelta(minutes=grace_minutes)


def day_groups(
    db: Session, *, day: date, family: bool = False, now: datetime | None = None
) -> list[dict[str, Any]]:
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
    # Item 6 auto-expiry: on the current day, drop occurrences finished >1h ago
    # (no-op for past/future days or when ``now`` isn't supplied).
    events = [
        ev
        for ev in events
        if not _occurrence_expired(day, ev.start_time, ev.end_time, now)
    ]
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
        if _occurrence_expired(day, occ.start_time, occ.end_time, now):
            continue
        gkey = _group_for(title=occ.title, tags=None, featured=False, recurring=True)
        rows_by_group[gkey].append(
            {
                "sort": time_sort_key(occ.start_time, occ.end_time),
                "time_label": short_time_label(occ.start_time, occ.end_time) or TIME_TBD_LABEL,
                "title": clean_event_title(occ.title, location_name=occ.venue),
                "venue": occ.venue,
                "url": occ.url,  # venue page — class series have no permalink
                "recurring": True,
            }
        )

    # "What's open for kids today": recurring family-venue hours (toddler
    # playground, pizza arcade, trampoline park, youth gym/dojo class blocks).
    # These are always kid/family things, so they join the Kids & Family group
    # regardless of the ?family filter and give a parent something to do even on
    # a day with no scheduled events. They sort after timed rows.
    rows_by_group["family"].extend(open_today_rows(day))

    groups: list[dict[str, Any]] = []
    for key, label, icon in GROUP_DEFS:
        rows = sorted(rows_by_group[key], key=lambda r: r["sort"])
        if not rows:
            continue  # omitted entirely — never an empty labeled shell
        group: dict[str, Any] = {
            "key": key, "label": label, "icon": icon, "count": len(rows), "rows": rows
        }
        if key == "classes" and len(rows) >= _CLASS_SUBGROUP_MIN:
            # Item 6: only sub-group dense class days; small days read fine flat.
            group["subgroups"] = _split_class_subgroups(rows)
        elif key == "family" and len(rows) >= _FAMILY_SUBGROUP_MIN:
            group["subgroups"] = _split_family_subgroups(rows)
        groups.append(group)
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
    sched_by_day: dict[date, dict[str, int]] = {}
    for occ in drop_event_duplicates(
        class_occurrences_in_window(db, window_start=start, window_end=end), event_keys
    ):
        if family and not is_family_event(occ.title):
            continue
        gkey = _group_for(title=occ.title, tags=None, featured=False, recurring=True)
        day_counts = sched_by_day.setdefault(occ.date, {})
        day_counts[gkey] = day_counts.get(gkey, 0) + 1

    rows: list[dict[str, Any]] = []
    for i in range(days):
        d = start + timedelta(days=i)
        counts = {key: 0 for key, _l, _i in GROUP_DEFS}
        for gkey, n in sched_by_day.get(d, {}).items():
            counts[gkey] = counts.get(gkey, 0) + n
        headline: dict[str, Any] | None = None
        best_key: tuple[int, int, time] | None = None
        for ev in by_day.get(d, []):
            tier = _event_tier(
                title=ev.title or "",
                tags=ev.tags,
                featured=bool(ev.featured),
                recurring=bool(ev.is_recurring),
            )
            counts[
                _group_for_tier(
                    tier,
                    recurring=bool(ev.is_recurring),
                    title=ev.title or "",
                    tags=ev.tags,
                )
            ] += 1
            if ev.is_recurring:
                continue  # a recurring class never headlines
            rank: tuple[int, int, time] = (tier, *time_sort_key(ev.start_time, ev.end_time))
            if best_key is None or rank < best_key:
                best_key = rank
                _time = short_time_label(ev.start_time, ev.end_time)
                headline = {
                    "title": clean_event_title(ev.title, location_name=ev.location_name),
                    "time": _time,
                    # 4.2: recurrence badge on the week-view headline. A one-off
                    # headline carrying an rrule/rdate (or flagged recurring) gets
                    # a cadence label ("Daily", "Mon–Fri", "Thu"); a true one-off
                    # gets None and the template omits the badge. The headline is
                    # still one event for this day — only a label is added.
                    "recurrence_label": event_recurrence_label(
                        ev, window_start=start, window_end=end, time_label=_time
                    ),
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
