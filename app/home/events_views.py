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

from app.core.timezone import occurrence_end_dt, to_lake_naive
from app.db.models import Event
from app.events.activity_taxonomy import (
    FALLBACK_LABEL,
    SUBGROUP_ORDER,
    classify_class_subgroup,
    split_class_subgroups,
    split_music_subgroups,
)
from app.events.class_occurrences import (
    class_occurrences_in_window,
    drop_event_duplicates,
)
from app.events.event_type_tags import event_type_label
from app.events.family_filter import is_family_event
from app.events.senior_filter import is_senior_event
from app.events.time_labels import TIME_TBD_LABEL, short_time_label, time_sort_key
from app.events.title_clean import clean_event_title
from app.home.event_buckets import (
    GROUP_DEFS,
    GROUP_NOUNS,
    TIER_SPECIAL,
    group_for_tier,
    is_dropin_rec,
)
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


# P1: the activity-type taxonomy (Yoga, Pilates, Martial Arts, …) that splits the
# "Fitness & classes" wall into typed subsections now lives in the shared
# :mod:`app.events.activity_taxonomy` module so ingest and render classify a
# class identically. These private aliases preserve the historical names this
# module's call sites and the test suite reference.
_class_subgroup = classify_class_subgroup
_split_class_subgroups = split_class_subgroups
_split_music_subgroups = split_music_subgroups
_CLASS_SUBGROUP_ORDER = SUBGROUP_ORDER
_CLASS_FALLBACK_LABEL = FALLBACK_LABEL
# P2: the Music & nightlife group splits into Live Music / Comedy & Theater the
# same way classes split — always (a 1-row threshold), empties omitted.
_MUSIC_SUBGROUP_MIN = 1
# P1: every class day is now typed into subsections (no flat untyped wall), so a
# single class still resolves to its activity subcategory. (Was 6 — small days
# used to render flat, which left items in the generic "Fitness & classes" bucket
# the brief calls out.)
_CLASS_SUBGROUP_MIN = 1


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
# P1: always type the Kids & Family list into youth-activity subsections (youth
# classes route here and must resolve to a typed Youth subcategory).
_FAMILY_SUBGROUP_MIN = 1


# Provider-derived class activity → its Youth subsection, so a youth class with
# a generic title ("Boys Athletics", "Elementary B") still types correctly once
# routed to Kids & Family (the provider already told us the discipline).
_ACTIVITY_TO_FAMILY_LABEL: dict[str, str] = {
    "Gymnastics": "Youth Gymnastics",
    "Dance": "Youth Dance",
    "Martial Arts": "Youth Martial Arts",
    "Aquatic fitness": "Swim Lessons",
}


def _family_subgroup(title: str, activity: str | None = None) -> str:
    """Map a Kids & Family occurrence to a youth-activity subsection.

    Title keyword wins (specific); otherwise the provider-derived ``activity``
    (Gymnastics/Dance/…) maps to its Youth subsection; else "More for kids"."""
    # Drop-in rec (Open Swim, Free Family Swim, Open Gym) is NOT a lesson/class —
    # it must not file under "Swim Lessons" (or any typed youth class) on the
    # "swim"/"gym" keyword. Route it to the general "More for kids" bucket.
    if is_dropin_rec(title):
        return _FAMILY_FALLBACK_LABEL
    low = title.lower()
    for label, hints in _FAMILY_SUBGROUPS:
        for h in hints:
            if re.search(r"\b" + re.escape(h) + r"(?:e?s|ing)?\b", low):
                return label
    if activity and activity in _ACTIVITY_TO_FAMILY_LABEL:
        return _ACTIVITY_TO_FAMILY_LABEL[activity]
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
            label = _family_subgroup(row.get("title") or "", row.get("activity"))
        buckets.setdefault(label, []).append(row)
    out: list[dict[str, Any]] = []
    for label in _FAMILY_SUBGROUP_ORDER:
        sub_rows = buckets.get(label)
        if sub_rows:
            out.append({"label": label, "rows": sub_rows, "count": len(sub_rows)})
    return out


ALL_DAY_LABEL = "All day"

# Titles whose 00:00 / no-end time genuinely means "runs all day" rather than
# "time unknown". The ingest convention overloads 00:00+None for both cases
# (see app.events.time_labels), so we can only safely promote the label to
# "All day" for titles that are unmistakably all-day drop-in rec — chiefly
# pickleball open play. Everything else keeps the honest "Time TBD".
_ALL_DAY_TITLE_RE = re.compile(r"\b(?:pickleball|open play)\b", re.IGNORECASE)


def _row_time_label(title: str, start_time: time | None, end_time: time | None) -> str:
    """Time chip for a day-view row.

    A known time renders normally ("8 AM"). When the time is unknown (the
    00:00/None convention), all-day rec titles read "All day" and everything
    else keeps "Time TBD" — we never fabricate a clock time.
    """
    label = short_time_label(start_time, end_time)
    if label is not None:
        return label
    if _ALL_DAY_TITLE_RE.search(title or ""):
        return ALL_DAY_LABEL
    return TIME_TBD_LABEL


def _event_row(ev: Event) -> dict[str, Any]:
    return {
        "sort": time_sort_key(ev.start_time, ev.end_time),
        "time_label": _row_time_label(ev.title or "", ev.start_time, ev.end_time),
        "title": clean_event_title(ev.title, location_name=ev.location_name),
        "venue": ev.location_name,
        "url": f"/events/{ev.id}",
        "recurring": bool(ev.is_recurring),
        # P2: the event TYPE folded into a scannable label ("Live Music",
        # "Comedy") + the raw tags so the music group can split into subsections.
        "tags": list(ev.tags or []),
        "type_label": event_type_label(ev.title, ev.tags, ev.location_name),
    }


def _route_occurrence(
    row: dict[str, Any],
    gkey: str,
    rows_by_group: dict[str, list[dict[str, Any]]],
    family_overlay: list[dict[str, Any]],
    senior_overlay: list[dict[str, Any]],
    *,
    is_family: bool,
    is_senior: bool,
) -> None:
    """Place a day-view row into its primary group + the age overlays.

    Seniors (2026-06-23 brief): EVERY senior item — senior fitness, senior social,
    senior-center programs — renders under the top-level Seniors group and ONLY
    there. No dual-listing into Fitness & classes (the live bug: "Water Wellness"
    showed under both Seniors and Aquatic fitness). So a senior occurrence routes
    to the Seniors overlay alone, never to its activity primary. (This supersedes
    the earlier "senior fitness may *also* appear under a Fitness Seniors
    subcategory" rule.)

    P1 age-awareness (Finding 11): a YOUTH *class* routes to Kids & Family ONLY —
    its typed Youth subsection — and is NOT duplicated into the adult Fitness
    list. Non-class youth items (festivals, story time) keep the additive overlay
    (they stay in their primary group AND re-list under Kids & Family for
    discoverability).
    """
    if is_senior:
        senior_overlay.append(row)
        return
    if is_family and gkey == "classes":
        family_overlay.append(row)
        return
    rows_by_group[gkey].append(row)
    if is_family:
        family_overlay.append(row)


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
    (no ``start_time``) never expire, and neither do all-day events
    (``start_time`` 00:00 with no ``end_time``). End is ``end_time`` when set, else
    ``start_time`` + ``default_minutes`` (Item 6 auto-expiry).
    """
    if now is None or start_time is None:
        return False
    now_local = to_lake_naive(now)
    if now_local.date() != day:
        return False
    # All-day events use the start=00:00 / end=None convention (the same test
    # the .ics feed and the pickleball/parks-rec loaders use). They have no real
    # end-of-day moment, so the ``default_minutes`` fallback below would place
    # their end at ~2 AM and wrongly purge them from the Today view a few hours
    # into every day — even though they run all day. Treat them like Time-TBD
    # rows: never expire on the current day (the date roll handles them).
    if start_time == time(0, 0) and end_time is None:
        return False
    # Shared end-moment resolution (handles the 00:00/cross-midnight convention),
    # so the feed, /events-ui, and the detail banner never disagree on "past".
    end_dt = occurrence_end_dt(day, start_time, end_time, default_minutes=default_minutes)
    if end_dt is None:
        return False
    return now_local > end_dt + timedelta(minutes=grace_minutes)


def day_groups(
    db: Session,
    *,
    day: date,
    family: bool = False,
    seniors: bool = False,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Category-accordion groups for one date. Empty groups are omitted.

    Rows inside each group sort chronologically with time-TBD rows last (the
    shared :func:`time_sort_key` contract). Venue Schedule classes join the
    Fitness & classes group, linking to their venue page; classes that also
    exist as Event rows are dropped by (title, date) so nothing shows twice.

    ``family=True`` (the ``?family=1`` toggle) keeps only occurrences that
    positively read as kid/family things (:func:`is_family_event`) — e.g. the
    Aquatic Center contributes Open Swim but not the adult exercise classes.
    ``seniors=True`` (the ``?seniors=1`` toggle) is the symmetric senior narrow
    (:func:`is_senior_event`). When either narrow is on, the Kids/Seniors
    overlays and the family-venue "open today" rows are suppressed — the whole
    view is already that audience. ``family`` wins if both are passed.
    """
    if family:
        seniors = False
    events = _live_events_by_day(db, window_start=day, window_end=day).get(day, [])
    if family:
        events = [ev for ev in events if is_family_event(ev.title, ev.tags)]
    elif seniors:
        events = [ev for ev in events if is_senior_event(ev.title, ev.tags, ev.location_name)]
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
    # Seniors is an additive overlay: every senior-tagged occurrence keeps its
    # primary group AND is re-listed under "Seniors", so there is one place to
    # find everything at the Senior Center. _group_for never returns "seniors",
    # so primaries are assigned first and this overlay is layered on after.
    # Kids & Family is an ADDITIVE overlay (2026-06-19), built the same way as
    # Seniors: a kid occurrence keeps its primary group AND is re-listed here.
    family_overlay: list[dict[str, Any]] = []
    senior_overlay: list[dict[str, Any]] = []
    for ev in events:
        gkey = _group_for(
            title=ev.title or "",
            tags=ev.tags,
            featured=bool(ev.featured),
            recurring=bool(ev.is_recurring),
        )
        row = _event_row(ev)
        _route_occurrence(
            row, gkey, rows_by_group, family_overlay, senior_overlay,
            is_family=(not family and not seniors and is_family_event(ev.title, ev.tags)),
            is_senior=(
                not family and not seniors
                and is_senior_event(ev.title, ev.tags, ev.location_name)
            ),
        )

    for occ in drop_event_duplicates(
        class_occurrences_in_window(db, window_start=day, window_end=day), event_keys
    ):
        if family and not is_family_event(occ.title):
            continue
        if seniors and not is_senior_event(occ.title, None, occ.venue):
            continue
        if _occurrence_expired(day, occ.start_time, occ.end_time, now):
            continue
        gkey = _group_for(title=occ.title, tags=None, featured=False, recurring=True)
        row = {
            "sort": time_sort_key(occ.start_time, occ.end_time),
            "time_label": _row_time_label(occ.title or "", occ.start_time, occ.end_time),
            "title": clean_event_title(occ.title, location_name=occ.venue),
            "venue": occ.venue,
            "url": occ.url,  # venue page — class series have no permalink
            "recurring": True,
            # Provider-derived activity (Yoga/Dance/Gymnastics/…) so the Fitness &
            # classes split (and the Youth split) can type a generically-named
            # class instead of dropping it into "Other classes".
            "activity": occ.provider_activity,
            # Permalink-less programs (no provider page) get a stable row id so
            # the home feed can deep-link to this exact row (#program-…) instead
            # of the whole-day list (Item 2). Provider-backed rows keep their own
            # link and need no anchor.
            "anchor": occ.anchor if not occ.url else None,
        }
        _route_occurrence(
            row, gkey, rows_by_group, family_overlay, senior_overlay,
            is_family=(not family and not seniors and is_family_event(occ.title)),
            is_senior=(
                not family and not seniors
                and is_senior_event(occ.title, None, occ.venue)
            ),
        )

    # "What's open for kids today": recurring family-venue hours (toddler
    # playground, pizza arcade, trampoline park, youth gym/dojo class blocks).
    # These are always kid/family things, so they join the Kids & Family group
    # and give a parent something to do even on a day with no scheduled events.
    # Suppressed in the seniors narrow (kid venues aren't a senior view). They
    # sort after timed rows.
    if not seniors:
        family_overlay.extend(open_today_rows(day))
    rows_by_group["family"] = family_overlay
    rows_by_group["seniors"].extend(senior_overlay)

    groups: list[dict[str, Any]] = []
    for key, label, icon in GROUP_DEFS:
        rows = sorted(rows_by_group[key], key=lambda r: r["sort"])
        if not rows:
            continue  # omitted entirely — never an empty labeled shell
        group: dict[str, Any] = {
            "key": key, "label": label, "icon": icon, "count": len(rows), "rows": rows
        }
        if key == "music" and len(rows) >= _MUSIC_SUBGROUP_MIN:
            # P2: typed Live Music / Comedy & Theater subsections under Music &
            # nightlife (mirrors the class subgroups; empties omitted).
            group["subgroups"] = _split_music_subgroups(rows)
        elif key == "classes" and len(rows) >= _CLASS_SUBGROUP_MIN:
            # P1: always type the Fitness & classes list into activity subsections
            # so no class sits in a generic untyped bucket.
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
    db: Session, *, start: date, days: int = 7, family: bool = False, seniors: bool = False
) -> list[dict[str, Any]]:
    """The next-``days`` rows for the week view (gap-free: contiguous dates).

    Every live event occurrence in the window is counted in exactly one day's
    rollup. The headline is the day's top ONE-OFF by ``(_event_tier, time)`` —
    a recurring class can never take it; days with no one-offs headline
    nothing and show only the rollup (or honest empty copy).

    ``family=True`` / ``seniors=True`` apply the same audience occurrence filter
    as :func:`day_groups`, so the week rollups agree with the day view.
    ``family`` wins if both are passed.
    """
    if family:
        seniors = False
    end = start + timedelta(days=days - 1)
    by_day = _live_events_by_day(db, window_start=start, window_end=end)
    if family:
        by_day = {
            d: [ev for ev in evs if is_family_event(ev.title, ev.tags)]
            for d, evs in by_day.items()
        }
    elif seniors:
        by_day = {
            d: [ev for ev in evs if is_senior_event(ev.title, ev.tags, ev.location_name)]
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
        if seniors and not is_senior_event(occ.title, None, occ.venue):
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
                    "type_label": event_type_label(ev.title, ev.tags, ev.location_name),
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


def _week_range_label(sunday: date) -> str:
    """"Jun 15 – 21" / "Jun 29 – Jul 5" for a Sun–Sat week starting ``sunday``."""
    saturday = sunday + timedelta(days=6)
    left = f"{sunday.strftime('%b')} {sunday.day}"
    if saturday.month == sunday.month:
        return f"{left} – {saturday.day}"
    return f"{left} – {saturday.strftime('%b')} {saturday.day}"


def swipe_weeks(
    db: Session,
    *,
    today: date,
    num_weeks: int = 5,
    family: bool = False,
    seniors: bool = False,
) -> list[dict[str, Any]]:
    """Consecutive Sun–Sat weeks for the mobile swipeable calendar (Item 3).

    Each week reuses :func:`week_rows` (so headlines / rollups match the week
    view and the day pages), anchored on the Sunday of the current week and
    running ``num_weeks`` weeks forward. ``is_today`` / ``label`` are recomputed
    from each day's real date (``week_rows`` only marks its first row "Today",
    which would be wrong for a week that doesn't start today). The week
    containing ``today`` is flagged ``is_current`` so the carousel can open on it.
    """
    sunday = today - timedelta(days=(today.weekday() + 1) % 7)  # Mon=0 → back to Sun
    weeks: list[dict[str, Any]] = []
    for w in range(num_weeks):
        ws = sunday + timedelta(days=7 * w)
        days = week_rows(db, start=ws, days=7, family=family, seniors=seniors)
        for row in days:
            d = date.fromisoformat(row["iso"])
            row["is_today"] = d == today
            row["label"] = "Today" if d == today else d.strftime("%a")
        weeks.append(
            {
                "label": _week_range_label(ws),
                "start_iso": ws.isoformat(),
                "is_current": ws <= today <= ws + timedelta(days=6),
                "days": days,
            }
        )
    return weeks


def day_highlights(
    db: Session, *, day: date, now: datetime | None = None, limit: int = 3
) -> list[dict[str, Any]]:
    """Top one-off events for the home "Today's highlights" strip — the unique,
    not-recurring things, ranked by tier (special first) then time. Recurring
    classes and all-day drop-in rec never headline. Empty day -> []."""
    events = _live_events_by_day(db, window_start=day, window_end=day).get(day, [])
    ranked: list[tuple[int, tuple[int, time], Event]] = []
    for ev in events:
        if ev.is_recurring:
            continue
        if _occurrence_expired(day, ev.start_time, ev.end_time, now):
            continue
        tier = _event_tier(
            title=ev.title or "", tags=ev.tags, featured=bool(ev.featured), recurring=False
        )
        ranked.append((tier, time_sort_key(ev.start_time, ev.end_time), ev))
    ranked.sort(key=lambda t: (t[0], t[1]))
    out: list[dict[str, Any]] = []
    for tier, _sk, ev in ranked[:limit]:
        out.append(
            {
                "title": clean_event_title(ev.title, location_name=ev.location_name),
                "time_label": short_time_label(ev.start_time, ev.end_time),
                "venue": ev.location_name,
                "special": tier == TIER_SPECIAL,
            }
        )
    return out
