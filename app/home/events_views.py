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

from app.core.timezone import to_lake_naive
from app.db.models import Event
from app.events.activity_taxonomy import (
    EVENTS_AROUND_LABEL,
    FALLBACK_LABEL,
    SUBGROUP_ORDER,
    activity_bucket,
    classify_class_subgroup,
    golf_venue_kind,
    resolve_activity,
    split_class_subgroups,
    split_events_subgroups,
    split_learn_subgroups,
    split_music_subgroups,
    split_senior_subgroups,
)
from app.events.class_occurrences import (
    class_occurrences_in_window,
    drop_event_duplicates,
)
from app.events.event_type_tags import event_type_label
from app.events.family_filter import is_family_event, is_youth_event
from app.events.senior_filter import is_senior_event
from app.events.time_labels import TIME_TBD_LABEL, short_time_label, time_sort_key
from app.events.title_clean import clean_event_title, clean_venue_label
from app.home.event_buckets import (
    GROUP_DEFS,
    GROUP_NOUNS,
    TIER_SPECIAL,
    group_for_tier,
    is_dropin_rec,
)
from app.home.family_venues import class_today_rows, funzone_hours_rows, open_today_rows
from app.home.sandstone import (
    _event_tier,
    _live_events_by_day,
    event_recurrence_label,
)
from app.movies.queries import movies_today

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


# The old Kids & Family overlay + its youth-activity sub-split (_FAMILY_SUBGROUPS)
# is retired (Casey 2026-06-26): there is no separate Kids & Family group. Youth
# items now peel into a "Youth <activity>" sub-section of their own group, built
# by the shared splits in app.events.activity_taxonomy (split_class_subgroups
# etc.), keyed off the per-row ``youth`` flag stamped in day_groups.


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


HOURS_VARY_LABEL = "Hours vary"


def _event_row(ev: Event) -> dict[str, Any]:
    tags = list(ev.tags or [])
    label = _row_time_label(ev.title or "", ev.start_time, ev.end_time)
    # A venue-hours row (facet:hours) with no real clock time reads "Hours vary"
    # rather than "Time TBD" — e.g. golf course/range/simulator all-day rows
    # (Casey 2026-06-26). Curated funzone-hours rows show real hours instead and
    # never reach this path.
    if label == TIME_TBD_LABEL and any(
        str(t).strip().lower() == "facet:hours" for t in tags
    ):
        label = HOURS_VARY_LABEL
    return {
        "sort": time_sort_key(ev.start_time, ev.end_time),
        "time_label": label,
        "title": clean_event_title(ev.title, location_name=ev.location_name),
        "venue": clean_venue_label(ev.location_name),
        "url": f"/events/{ev.id}",
        "recurring": bool(ev.is_recurring),
        # P2: the event TYPE folded into a scannable label ("Live Music",
        # "Comedy") + the raw tags so the music group can split into subsections.
        "tags": tags,
        "type_label": event_type_label(ev.title, ev.tags, ev.location_name),
    }


# Activity slugs whose DB ``facet:hours`` rows are superseded at render time by
# the curated funzone venue-hours rows (which carry real "12–11 PM" times instead
# of "Time TBD"). The loader stopped emitting these all-day hours rows; any that
# linger in the window are render-filtered so they don't double up with curated.
_FUNZONE_HOURS_SLUGS: frozenset[str] = frozenset(
    {"bowling", "billiards", "trampoline", "family-fun"}
)


def _is_funzone_db_hours(tags: list[str] | None) -> bool:
    """True for a DB Event row that is a funzone venue's all-day hours line
    (``activity:<bowling|billiards|trampoline|family-fun>`` + ``facet:hours``) —
    superseded by the curated funzone-hours rows, so it is dropped at render."""
    tagset = {str(t).strip().lower() for t in (tags or [])}
    if "facet:hours" not in tagset:
        return False
    return any(f"activity:{slug}" in tagset for slug in _FUNZONE_HOURS_SLUGS)


def _row_has_special(row: dict[str, Any]) -> bool:
    """True when a row carries a themed-special or competition facet."""
    tagset = {str(t).strip().lower() for t in (row.get("tags") or [])}
    return bool(tagset & {"facet:special", "facet:competition"})


def _row_is_event(row: dict[str, Any]) -> bool:
    """True when a row is a real **event** for the auto-expand rule (Casey
    2026-06-26): a one-off / dated local happening (market, festival, concert,
    car show…) OR a themed special / competition. NOT an event (a listing →
    never forces a section open): recurring fitness/workshop classes, venue hours
    (``facet:hours`` / curated ``ongoing``), and drop-in / open-play rec."""
    if _row_has_special(row):
        return True
    if row.get("ongoing"):
        return False  # curated venue-hours row
    tagset = {str(t).strip().lower() for t in (row.get("tags") or [])}
    if "facet:hours" in tagset:
        return False  # venue hours line
    title = row.get("title") or ""
    if is_dropin_rec(title):
        return False  # open swim / open play
    slug = resolve_activity(title, row.get("venue"), row.get("tags"), row.get("activity"))
    if activity_bucket(slug) in ("classes", "learn"):
        return False  # a fitness/workshop class is a listing, not an event
    return True


def _explicit_activity_bucket(tags: list[str] | None) -> str | None:
    """The top-level bucket of an EXPLICIT ``activity:<slug>`` tag (ingest/loader
    stamped), or None when the row carries no such tag. Distinct from
    ``resolve_activity`` (which also classifies from the title) so we can let an
    explicitly-stamped tag be authoritative without changing classifier-only
    inference on legacy untagged rows."""
    for t in tags or []:
        s = str(t)
        if s.startswith("activity:"):
            return activity_bucket(s.split(":", 1)[1] or None)
    return None


def _occurrence_group_keys(
    gkey: str,
    *,
    title: str,
    venue: str | None,
    activity: str | None,
    tags: list[str] | None = None,
    is_senior: bool,
) -> list[str]:
    """The group key(s) the day view renders this occurrence under.

    The single source of truth for placement, shared by the day accordion
    (:func:`_route_occurrence`) and the week/month rollup counts
    (:func:`week_rows`), so the two agree by construction.

    No-overlay model (Casey 2026-06-26): every occurrence lands in exactly ONE
    group — there is no additive "Kids & Family" cross-list. Youth-specific items
    stay in their primary group and are peeled into that group's "Youth & Family"
    sub-section at render. The Seniors GATE is the one exclusive route (gated
    programming lives under Seniors only). Otherwise the canonical
    ``activity:<slug>`` tag routes the non-fitness activities — arts/cooking/maker/
    learning → **learn**, theater → **music**, games/bowling/billiards/trampoline/
    family-fun → **events** — and an explicit fitness-bucket venue-hours tag pulls
    golf/pickleball hours into **classes**; everything else keeps its tier group.
    """
    # Senior gate FIRST: Senior-Center programming is gated and lives under
    # Seniors ONLY — never cross-listed into the public buckets.
    if is_senior:
        return ["seniors"]
    slug = resolve_activity(title, venue, tags, activity)
    abkt = activity_bucket(slug)
    # Golf splits by venue type (Phase 2, Casey 2026-06-26): the Top Tracer range
    # and indoor simulators are drop-in entertainment → Things to Do; the courses
    # are structured play → Sports & Fitness. ``venue-kind:*`` is stamped by the
    # golf loader (app.contrib.lhc_golf). Untagged golf falls through to the
    # default fitness routing below (so it stays in Sports & Fitness for now).
    if slug == "golf":
        vk = golf_venue_kind(tags)
        if vk in ("simulator", "range"):
            return ["events"]
        if vk == "course":
            return ["classes"]
    # Pickleball is the ONE drop-in exception (Phase 4, Casey 2026-06-26): "Open
    # Play" is pickleball's normal format, so every pickleball row stays in Sports
    # & Fitness → Pickleball (court hours / open play / leagues) rather than being
    # pulled into Things to Do by the drop-in-rec rule below.
    if slug == "pickleball":
        return ["classes"]
    # Classes & workshops (Phase 4c, Casey 2026-06-26): non-fitness instruction
    # (arts/craft/cooking/maker/learning) folds into Things to Do as a "Classes &
    # workshops" subcategory rather than its own top-level "learn" section.
    if abkt == "learn":
        return ["events"]
    if slug == "theater":
        return ["music"]
    if abkt == "events" and slug:  # games / bowling / billiards / trampoline / family-fun
        return ["events"]
    # An EXPLICIT ingest/loader-stamped activity tag in the fitness bucket is
    # authoritative for placement: golf/pickleball venue hours carry
    # activity:<slug> + facet:hours/open-play but their venue-hours titles don't
    # trip the keyword tier classifier, so without this they'd fall to "Things to
    # Do" instead of Fitness & Sports → their subgroup. A court/venue-hours facet
    # (``facet:open-play``/``facet:hours``) overrides the drop-in-rec exception,
    # while a bare drop-in (Open Swim/Gym with no such facet) stays in Things to Do.
    if gkey != "classes" and _explicit_activity_bucket(tags) == "classes":
        tagset = {str(t).strip().lower() for t in (tags or [])}
        is_venue_hours = bool(tagset & {"facet:open-play", "facet:hours"})
        if is_venue_hours or not is_dropin_rec(title):
            return ["classes"]
    # A non-fitness recurring "class" with no activity type (the honest "Other
    # classes" residue) reads as a happening, not a fitness class → Things to Do.
    if gkey == "classes" and classify_class_subgroup(title, venue, activity) == FALLBACK_LABEL:
        return ["events"]
    return [gkey]


def _route_occurrence(
    row: dict[str, Any],
    gkey: str,
    rows_by_group: dict[str, list[dict[str, Any]]],
    senior_overlay: list[dict[str, Any]],
    *,
    is_senior: bool,
) -> None:
    """Place a day-view row into its single group (no-overlay model, Casey
    2026-06-26).

    Seniors is the one gated, EXCLUSIVE route: a senior occurrence renders under
    the Seniors group ONLY, never its activity primary. Everything else lands in
    exactly one primary group (:func:`_occurrence_group_keys`); youth-specific
    items stay there and are peeled into that group's "Youth & Family" sub-section
    at render — they are no longer duplicated into a separate Kids & Family group.
    """
    for key in _occurrence_group_keys(
        gkey,
        title=row.get("title") or "",
        venue=row.get("venue"),
        activity=row.get("activity"),
        tags=row.get("tags"),
        is_senior=is_senior,
    ):
        if key == "seniors":
            senior_overlay.append(row)
        else:
            rows_by_group[key].append(row)


def _occurrence_expired(
    day: date,
    start_time: time | None,
    end_time: time | None,
    now: datetime | None,
    *,
    minutes_after_start: int = 60,
) -> bool:
    """True if an occurrence on ``day`` started more than ``minutes_after_start`` ago.

    The calendar rule (2026-06-24): items and movies drop off the day's list one
    hour after they *start*, not after they end — once something has been going an
    hour it's effectively too late to head out for it, so it stops cluttering the
    "what's on today" view. This is deliberately a START-based cutoff: a long
    festival that began over an hour ago is hidden even though it is still running.

    No-op (returns False) unless ``now`` is given and ``day`` is the current day,
    so the filter only ever trims *today's* started items (past days drop via the
    date roll; future days are untouched). Time-TBD occurrences (no ``start_time``)
    never expire, and neither do all-day listings, which carry the
    ``start_time`` 00:00 / ``end_time`` None sentinel (the .ics feed and the
    pickleball/parks-rec loaders use it for "runs all day") — they have no real
    start moment to count an hour from. ``end_time`` is used *only* to detect that
    sentinel; a genuine occurrence that starts at 00:00 *with* an explicit end is
    timed normally (expires an hour after its 00:00 start).

    Note this no longer mirrors the event-detail "passed" banner
    (:func:`app.main._event_is_past`), which stays END-based — a page you open
    directly should say "passed" only once the event has actually ended, even if
    it already dropped off the today list.
    """
    if now is None or start_time is None:
        return False
    now_local = to_lake_naive(now)
    if now_local.date() != day:
        return False
    # All-day sentinel (00:00 start, no end): no real start moment, so never
    # expire on the current day — the date roll handles it.
    if start_time == time(0, 0) and end_time is None:
        return False
    start_dt = datetime.combine(day, start_time)
    return now_local > start_dt + timedelta(minutes=minutes_after_start)


def day_groups(
    db: Session,
    *,
    day: date,
    family: bool = False,
    seniors: bool = False,
    now: datetime | None = None,
    events_only: bool = False,
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

    ``events_only=True`` keeps only dated happenings (``_row_is_event`` True) —
    venue hours and recurring class rosters are skipped. Used by the legacy month
    grid and the week rollups; the unified calendar (:func:`calendar_day_view_model`)
    passes ``events_only=False`` so hours + classes render inline. Themed
    ``facet:special`` / ``facet:competition`` rows are NOT split into a separate
    group (Phase 3, 2026-06-26) — they render inline under their venue subcategory.
    """
    if family:
        seniors = False
    events = _live_events_by_day(db, window_start=day, window_end=day).get(day, [])
    if family:
        events = [ev for ev in events if is_family_event(ev.title, ev.tags, ev.location_name)]
    elif seniors:
        events = [ev for ev in events if is_senior_event(ev.title, ev.tags, ev.location_name)]
    # Auto-expiry: on the current day, drop occurrences that started >1h ago
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
    # Seniors is the one gated, EXCLUSIVE overlay: every senior-tagged occurrence
    # renders under "Seniors" only (never its activity primary). There is no
    # Kids & Family overlay any more (Casey 2026-06-26) — youth-specific items
    # stay in their primary group and peel into a "Youth <activity>" sub there.
    senior_overlay: list[dict[str, Any]] = []
    overlay_ok = not family and not seniors  # overlays/youth subs off under a narrow
    for ev in events:
        # Funzone venue HOURS now render from the curated registry (real times),
        # so drop any lingering DB all-day funzone hours row to avoid a duplicate.
        # The themed funzone EVENTS (facet:special cosmic/glow) are NOT dropped.
        if _is_funzone_db_hours(ev.tags):
            continue
        gkey = _group_for(
            title=ev.title or "",
            tags=ev.tags,
            featured=bool(ev.featured),
            recurring=bool(ev.is_recurring),
        )
        row = _event_row(ev)
        is_senior = overlay_ok and is_senior_event(ev.title, ev.tags, ev.location_name)
        # Youth-specific items are peeled into a "Youth <activity>" sub-section of
        # their own group at render — flagged here (off under a narrow / for seniors).
        row["youth"] = (
            overlay_ok and not is_senior
            and is_youth_event(ev.title, ev.tags, ev.location_name)
        )
        _route_occurrence(row, gkey, rows_by_group, senior_overlay, is_senior=is_senior)

    # Venue Schedule classes are Places & Ongoing content (recurring rosters),
    # never Calendar happenings — skip them entirely on the events-only surface.
    _sched_occs = (
        []
        if events_only
        else drop_event_duplicates(
            class_occurrences_in_window(db, window_start=day, window_end=day), event_keys
        )
    )
    for occ in _sched_occs:
        if family and not is_family_event(occ.title, None, occ.venue):
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
            "venue": clean_venue_label(occ.venue),
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
        is_senior = overlay_ok and is_senior_event(occ.title, None, occ.venue)
        row["youth"] = (
            overlay_ok and not is_senior and is_youth_event(occ.title, None, occ.venue)
        )
        _route_occurrence(row, gkey, rows_by_group, senior_overlay, is_senior=is_senior)

    # Youth studio classes (martial arts / gymnastics, real published times) join
    # Fitness & Sports and peel into their "Youth Martial Arts" / "Youth
    # Gymnastics" sub via the row's provider activity. Suppressed in the seniors
    # narrow; in the family narrow the whole view is kids so no youth sub is added.
    if not seniors and not events_only:
        for r in class_today_rows(day):
            r["youth"] = not family
            rows_by_group["classes"].append(r)
    rows_by_group["seniors"].extend(senior_overlay)

    # Things to Do → the Bowling/Billiards/Trampoline/Arcade venue-type cluster:
    # curated venue hours (real "12–11 PM" times) injected here so each venue type
    # shows its hours alongside its events (cosmic/glow). All-ages venues, so NOT
    # youth — they sit under their venue type, never duplicated. Suppressed under a
    # narrow (the family/senior narrow is already that audience).
    if overlay_ok and not events_only:
        rows_by_group["events"].extend(funzone_hours_rows(day))

    # Events-only mode (legacy month grid / week rollups): keep only dated
    # happenings — venue hours and recurring class rosters are filtered out.
    # Phase 3 (Casey 2026-06-26): themed specials / competitions are NO LONGER
    # peeled into a separate "Special sessions" group; they render INLINE under
    # their venue subcategory (a Cosmic / Glow / Rock & Bowl night sits beside
    # Bowling's hours), so a no-special day simply shows the hours.
    if events_only:
        for key in list(rows_by_group):
            rows_by_group[key] = [r for r in rows_by_group[key] if _row_is_event(r)]

    groups: list[dict[str, Any]] = []
    for key, label, icon in GROUP_DEFS:
        rows = sorted(rows_by_group[key], key=lambda r: r["sort"])
        if not rows:
            continue  # omitted entirely — never an empty labeled shell
        group: dict[str, Any] = {
            "key": key, "label": label, "icon": icon, "count": len(rows), "rows": rows
        }
        if key == "events":
            # Things to Do splits by VENUE TYPE (Casey 2026-06-26): Around Town +
            # Games & Social + Billiards / Bowling / Trampoline / Arcade & Family
            # Fun (each venue type holds its hours AND its events). Applied only
            # when a non-residual subsection is present, so a bare market day stays
            # a flat list.
            subs = split_events_subgroups(rows)
            if any(s["label"] != EVENTS_AROUND_LABEL for s in subs):
                group["subgroups"] = subs
        elif key == "music" and len(rows) >= _MUSIC_SUBGROUP_MIN:
            # P2: typed Live Music / Comedy & Theater subsections under Music &
            # nightlife (mirrors the class subgroups; empties omitted).
            group["subgroups"] = _split_music_subgroups(rows)
        elif key == "classes" and len(rows) >= _CLASS_SUBGROUP_MIN:
            # P1: always type the Fitness & classes list into activity subsections
            # so no class sits in a generic untyped bucket.
            group["subgroups"] = _split_class_subgroups(rows)
        elif key == "learn":
            # Phase 2 (2026-06-25): Classes & Workshops splits into Arts & Crafts /
            # Paint & Sip / Cooking / Maker / Lifelong Learning.
            group["subgroups"] = split_learn_subgroups(rows)
        elif key == "seniors":
            # Phase 2 (2026-06-25): the gated Seniors group sub-splits internally
            # (Games & Social / Fitness & Movement / Arts & Crafts / Social-Music-
            # Meals / Special) so it stays browsable.
            group["subgroups"] = split_senior_subgroups(rows)
        groups.append(group)
    # Default expand/collapse (Casey 2026-06-26): a group — and each of its
    # sub-sections — opens by default ONLY when it contains a real EVENT (a
    # one-off happening, a themed special, or a competition). Classes-and-hours-
    # only groups stay collapsed, and an event-less day loads fully collapsed.
    # The gated Seniors group never auto-opens on its routine weekly programming —
    # only a genuine senior special/competition opens it.
    for g in groups:
        if g["key"] == "seniors":
            g["open"] = any(_row_has_special(r) for r in g["rows"])
        else:
            g["open"] = any(_row_is_event(r) for r in g["rows"])
        # Subcategories stay collapsed until expanded (spec §5.3); only the
        # top-level header auto-opens on a real event.
        for sub in g.get("subgroups", []):
            sub["open"] = False
    return groups


# Surface B — Places & Ongoing top-level categories (two-surface spec §3), in
# order. These are render groups for the Places browse tab only; they are NOT
# part of the shared Calendar GROUP_DEFS. Subcategories (§4) land in Phase 3.
PLACES_GROUP_DEFS: tuple[tuple[str, str, str], ...] = (
    ("things-to-do", "Things to Do", "\U0001F3B3"),   # bowling/billiards/trampoline/on-water/workshops
    ("sports-fitness", "Sports & Fitness", "\U0001F3C3"),  # golf/pickleball/gymnastics/martial/yoga/dance
    ("seniors", "Seniors", "\U0001F9D3"),              # gated Senior-Center programming (§5.2)
)


def _places_top_key(primary_key: str) -> str:
    """Map a Calendar primary-group key to its Places & Ongoing top-level (§3).

    Sports/fitness classes (``classes``) → "Sports & Fitness"; gated senior
    programming (``seniors``) → "Seniors"; everything else (funzone venues →
    ``events``, lake rentals → ``water``, standing studios → ``learn``) →
    "Things to Do".
    """
    if primary_key == "classes":
        return "sports-fitness"
    if primary_key == "seniors":
        return "seniors"
    return "things-to-do"


# Things-to-Do subcategory labels that aren't venue-type sections (spec §4).
PLACES_ON_THE_WATER_LABEL = "On the Water"
PLACES_WORKSHOPS_LABEL = "Classes & Workshops"


def _places_subgroups(key: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Subcategory split for one Places top-level (spec §4). Sports & Fitness
    splits by activity (Golf / Pickleball / Gymnastics / Martial arts / Yoga /
    Dance, each with its Youth third level); Seniors by its internal sections;
    Things to Do by venue type (Bowling / Billiards / Trampoline / Arcade) plus
    On the Water and a single Classes & Workshops section. Empty subsections are
    omitted by the shared splits (honest-omission)."""
    if key == "sports-fitness":
        return split_class_subgroups(rows)
    if key == "seniors":
        return split_senior_subgroups(rows)
    # Things to Do: partition by primary first so lake-rental and studio-workshop
    # rows aren't misfiled by the venue-type classifier.
    events_rows = [r for r in rows if r.get("_pk") == "events"]
    water_rows = [r for r in rows if r.get("_pk") == "water"]
    learn_rows = [r for r in rows if r.get("_pk") == "learn"]
    subs = split_events_subgroups(events_rows) if events_rows else []
    if water_rows:
        subs.append(
            {"label": PLACES_ON_THE_WATER_LABEL, "rows": water_rows, "count": len(water_rows)}
        )
    if learn_rows:
        subs.append(
            {"label": PLACES_WORKSHOPS_LABEL, "rows": learn_rows, "count": len(learn_rows)}
        )
    return subs


def _places_dedupe_key(row: dict[str, Any]) -> tuple[str, str]:
    """De-dup identity for a Places row: one entry per (title, venue). Places is
    a browse-anytime list, so a weekly class / venue-hours row that recurs every
    day in the window collapses to a single entry (spec §3)."""
    return (
        (row.get("title") or "").strip().lower(),
        (row.get("venue") or "").strip().lower(),
    )


def places_groups(
    db: Session,
    *,
    today: date,
    days: int = 7,
    family: bool = False,
) -> list[dict[str, Any]]:
    """Surface B — Places & Ongoing: the standing venues + weekly class schedules
    (two-surface spec §3), de-duplicated to one row per place/class across the
    window and grouped into the three top-level Places categories.

    This is the complement of the events-only Calendar (:func:`day_groups` with
    ``events_only=True``): it collects exactly the rows the Calendar drops —
    ``_row_is_event`` False (venue hours, curated ``ongoing`` rows, drop-in rec,
    recurring fitness/workshop class rosters). Subcategories and collapse/empty-
    hiding refinements are Phase 3; this builds the top-level browse groups.

    De-dup keeps the FIRST row seen per ``(title, venue)``; sources are scanned
    curated-first (funzone venue hours, then youth studio classes, then venue
    Schedule classes, then DB rows, then family open-hours) so the richest /
    most-specific row wins for a venue that appears in more than one source.
    """
    end = today + timedelta(days=days - 1)
    by_top: dict[str, list[dict[str, Any]]] = {key: [] for key, _l, _i in PLACES_GROUP_DEFS}
    seen: set[tuple[str, str]] = set()

    def _consider(row: dict[str, Any], *, recurring: bool) -> None:
        if not row.get("title"):
            return
        if _row_is_event(row):
            return  # belongs on the Calendar surface, not Places
        if family and not is_family_event(row.get("title"), row.get("tags"), row.get("venue")):
            return
        key = _places_dedupe_key(row)
        if key in seen:
            return
        seen.add(key)
        title = row.get("title") or ""
        venue = row.get("venue")
        tags = row.get("tags")
        activity = row.get("activity")
        is_senior = is_senior_event(title, tags, venue)
        gkey = _group_for(title=title, tags=tags, featured=False, recurring=recurring)
        primary = _occurrence_group_keys(
            gkey, title=title, venue=venue, activity=activity, tags=tags, is_senior=is_senior
        )[0]
        row["_pk"] = primary  # remembered for the Places subcategory split (§4)
        # Youth peels into a third-level "Youth <activity>" sub (§4); off under the
        # family narrow (the whole view is already kids) and never for seniors. A
        # row that already declares youth (youth-studio classes) keeps it.
        if family:
            row["youth"] = False
        elif "youth" not in row:
            row["youth"] = not is_senior and is_youth_event(title, tags, venue)
        by_top[_places_top_key(primary)].append(row)

    # Curated venue-hours rows first (real "12–11 PM" times + venue-kind tags), so
    # they win de-dup over any DB/family twin of the same venue.
    day = today
    while day <= end:
        for r in funzone_hours_rows(day):
            _consider(r, recurring=False)
        for r in class_today_rows(day):
            _consider(r, recurring=True)
        day += timedelta(days=1)
    for occ in class_occurrences_in_window(db, window_start=today, window_end=end):
        _consider(
            {
                "sort": time_sort_key(occ.start_time, occ.end_time),
                "time_label": _row_time_label(occ.title or "", occ.start_time, occ.end_time),
                "title": clean_event_title(occ.title, location_name=occ.venue),
                "venue": clean_venue_label(occ.venue),
                "url": occ.url,
                "recurring": True,
                "activity": occ.provider_activity,
            },
            recurring=True,
        )
    for _d, evs in _live_events_by_day(db, window_start=today, window_end=end).items():
        for ev in evs:
            if _is_funzone_db_hours(ev.tags):
                continue  # superseded by the curated funzone-hours rows above
            _consider(_event_row(ev), recurring=bool(ev.is_recurring))
    day = today
    while day <= end:
        for r in open_today_rows(day):
            _consider(r, recurring=False)
        day += timedelta(days=1)

    groups: list[dict[str, Any]] = []
    for key, label, icon in PLACES_GROUP_DEFS:
        rows = sorted(by_top[key], key=lambda r: (r.get("title") or "").lower())
        if not rows:
            continue  # hide empty categories (spec §5.3)
        subs = _places_subgroups(key, rows)
        for sub in subs:
            sub["open"] = False  # subcategories collapsed until expanded (§5.3)
        groups.append(
            {
                "key": key,
                "label": label,
                "icon": icon,
                "count": len(rows),
                "rows": rows,
                "subgroups": subs,
                "open": True,  # top-level header expanded; subcategories collapsed
            }
        )
    return groups


def calendar_day_view_model(
    db: Session,
    *,
    day: date,
    now: datetime | None = None,
    family: bool = False,
    seniors: bool = False,
) -> dict[str, Any]:
    """THE single Calendar-surface builder (parity refactor, Rule 0 2026-06-26;
    UNIFY flip, Rule 0b 2026-06-26).

    Returns the one canonical nested tree that **every** Calendar surface renders
    identically — ``/events-ui`` (``serve_events_ui``), the v4 home feed
    (``redesign.feed_view_model``), and the month agenda (``redesign._agenda``) —
    so they can never drift again. The tree is the **full** ``day_groups`` output
    (``events_only`` OFF — Rule 0b unifies the old two-surface split: venue hours
    and recurring classes now render inline as collapsed standing-content sections
    instead of living on a separate ``?view=places`` tab) plus a first-class
    **At the Movies** section (showtimes aren't Event-table rows, so they ride in
    their own ``is_movies`` section, slotted after Events).

    Cleanliness comes from collapse, not a second tab: each section auto-opens only
    when it holds a real happening (``day_groups`` sets ``open`` via
    ``_row_is_event``), so the day leads with what's on and standing venue hours /
    class rosters sit collapsed below.

    ``sections`` is the ordered list; ``total`` is the summed count. Consumers
    style rows in their own theme but MUST keep this structure (the parity test
    ``tests/test_home_calendar_parity.py`` asserts the (section, subgroup, count,
    order) tuples match across surfaces).
    """
    sections = day_groups(
        db, day=day, family=family, seniors=seniors, now=now, events_only=False
    )
    movies = movies_today(db, day=day, now=now)
    if movies:
        movies_section: dict[str, Any] = {
            "key": "movies",
            "label": "At the Movies",
            "icon": "\U0001F3AC",
            "count": len(movies),
            "rows": movies,
            "is_movies": True,
            "open": False,
        }
        anchor = next((i for i, s in enumerate(sections) if s["key"] == "events"), -1)
        sections.insert(anchor + 1, movies_section)
    return {"sections": sections, "total": sum(int(s.get("count") or 0) for s in sections)}


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
    db: Session,
    *,
    start: date,
    days: int = 7,
    family: bool = False,
    seniors: bool = False,
    events_only: bool = False,
) -> list[dict[str, Any]]:
    """The next-``days`` rows for the week view (gap-free: contiguous dates).

    Every live event occurrence in the window is counted in exactly one day's
    rollup. The headline is the day's top ONE-OFF by ``(_event_tier, time)`` —
    a recurring class can never take it; days with no one-offs headline
    nothing and show only the rollup (or honest empty copy).

    ``family=True`` / ``seniors=True`` apply the same audience occurrence filter
    as :func:`day_groups`, so the week rollups agree with the day view.
    ``family`` wins if both are passed.

    ``events_only=True`` counts only dated happenings (``_row_is_event`` True):
    venue Schedule classes and curated venue-hours rows are not counted. Themed
    special / competition rows count under their routed group (they render inline
    there — there is no separate "Special sessions" group; Phase 3, 2026-06-26).
    """
    if family:
        seniors = False
    end = start + timedelta(days=days - 1)
    by_day = _live_events_by_day(db, window_start=start, window_end=end)
    if family:
        by_day = {
            d: [ev for ev in evs if is_family_event(ev.title, ev.tags, ev.location_name)]
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
    _sched_occs = (
        []
        if events_only
        else drop_event_duplicates(
            class_occurrences_in_window(db, window_start=start, window_end=end), event_keys
        )
    )
    for occ in _sched_occs:
        if family and not is_family_event(occ.title, None, occ.venue):
            continue
        if seniors and not is_senior_event(occ.title, None, occ.venue):
            continue
        gkey = _group_for(title=occ.title, tags=None, featured=False, recurring=True)
        # Count into the SAME group the day view renders this under (Seniors gate /
        # Happening-today re-routes), not the bare primary — so the week rollup
        # can't disagree with the day. The senior gate is suppressed under a narrow.
        overlay_ok = not family and not seniors
        day_counts = sched_by_day.setdefault(occ.date, {})
        for key in _occurrence_group_keys(
            gkey,
            title=occ.title or "",
            venue=occ.venue,
            activity=occ.provider_activity,
            is_senior=overlay_ok and is_senior_event(occ.title, None, occ.venue),
        ):
            day_counts[key] = day_counts.get(key, 0) + 1

    rows: list[dict[str, Any]] = []
    for i in range(days):
        d = start + timedelta(days=i)
        counts = {key: 0 for key, _l, _i in GROUP_DEFS}
        for gkey, n in sched_by_day.get(d, {}).items():
            counts[gkey] = counts.get(gkey, 0) + n
        # Mirror the curated rows the day view injects (youth studio classes →
        # Fitness; funzone venue hours → Things to Do) so the rollup agrees with
        # the rendered group counts. Suppressed under a narrow, same as the day.
        if not seniors and not events_only:
            counts["classes"] += len(class_today_rows(d))
        if not family and not seniors and not events_only:
            counts["events"] += len(funzone_hours_rows(d))
        headline: dict[str, Any] | None = None
        best_key: tuple[int, int, time] | None = None
        for ev in by_day.get(d, []):
            if events_only and not _row_is_event(_event_row(ev)):
                continue  # Calendar: skip recurring classes / venue-hours rows
            tier = _event_tier(
                title=ev.title or "",
                tags=ev.tags,
                featured=bool(ev.featured),
                recurring=bool(ev.is_recurring),
            )
            ev_gkey = _group_for_tier(
                tier,
                recurring=bool(ev.is_recurring),
                title=ev.title or "",
                tags=ev.tags,
            )
            overlay_ok = not family and not seniors
            for key in _occurrence_group_keys(
                ev_gkey,
                title=ev.title or "",
                venue=ev.location_name,
                activity=None,
                tags=list(ev.tags or []),
                is_senior=overlay_ok and is_senior_event(ev.title, ev.tags, ev.location_name),
            ):
                counts[key] += 1
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
    events_only: bool = False,
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
        days = week_rows(
            db, start=ws, days=7, family=family, seniors=seniors, events_only=events_only
        )
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
