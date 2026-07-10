"""Data assembly for the Sandstone home (Ask) page.

Every figure here comes from a live query or is omitted — never a placeholder.
The prototype's hardcoded counts ("280 places", "12 happy hours", "448.7 ft")
are deliberately NOT reproduced: a tile with no live source is left out, and the
anti-confabulation contract in 01_UI_BUILD_GUIDE.md §4 is the spec.

Kept separate from ``router.py`` so the route stays a thin assembler and these
builders are unit-testable in isolation.
"""

from __future__ import annotations

import calendar as _calendar
import re
import weakref
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Event
from app.events.class_occurrences import (
    class_occurrences_in_window,
    drop_event_duplicates,
    feed_visible_occurrences,
)
from app.events.dedup import dedup_cross_source_occurrences
from app.events.recurrence import expand_event, occurrences_in_window
from app.events.series import schedule_label as _schedule_label
from app.events.time_labels import format_short_time, short_time_label, time_sort_key
from app.events.title_clean import clean_event_title
from app.home.activity import strip_activity
from app.home.event_buckets import (
    GROUP_DEFS,
    TIER_AQUATIC,
    TIER_CLASS,
    TIER_COMMUNITY,
    TIER_MUSIC,
    TIER_OTHER,
    TIER_SPECIAL,
    TIER_WATER,
    group_for_tier,
    is_civic,
)

# Re-export the bucket vocabulary under the historical private names that this
# module's call sites and the test suite (``sandstone._TIER_*``) reference. The
# canonical definitions live in :mod:`app.home.event_buckets` (Slice C). Plain
# assignment (not ``import ... as``) keeps ruff's isort happy under the project's
# combine-as-imports=false default.
_TIER_AQUATIC = TIER_AQUATIC
_TIER_CLASS = TIER_CLASS
_TIER_COMMUNITY = TIER_COMMUNITY
_TIER_MUSIC = TIER_MUSIC
_TIER_OTHER = TIER_OTHER
_TIER_SPECIAL = TIER_SPECIAL
_TIER_WATER = TIER_WATER
_group_for_tier = group_for_tier


# Per-Session memo for _live_events_by_day (audit 2026-07-01): one render used
# to run the full recurring-event fetch + RRULE expansion + render dedup for
# the SAME window several times (/events-ui week view computed the current week
# twice; the v4 home re-derives overlapping windows). Sessions are per-request
# (get_db) and these are read-only surfaces, so caching by (session, window) is
# safe; the WeakKeyDictionary lets the Session (and its memo) be garbage-
# collected at request end.
_LIVE_EVENTS_MEMO: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _live_events_by_day(
    db: Session, *, window_start: date, window_end: date
) -> dict[date, list[Event]]:
    """Live events bucketed by *occurrence* date across the inclusive window.

    Memoized per (Session, window) — see ``_LIVE_EVENTS_MEMO`` above.

    Events with a real schedule (``rrule``/``rdate``) are expanded via
    :func:`app.events.recurrence.occurrences_in_window`, so a weekly class shows
    on every occurrence in the window — not only on its stored start date — the
    same expansion ``/events-ui`` uses. Separately, any event whose *stored* date
    falls in the window is included on that date. This second pass is load-bearing:
    a row flagged ``is_recurring`` but carrying no rrule/rdate (a materialised
    single instance) would otherwise expand to nothing and vanish. Each
    ``(event, date)`` pair is emitted once, then cross-source duplicates of the
    same (title, date) occurrence (two scrapers carrying one real-world event)
    collapse to a single survivor via
    :func:`app.events.dedup.dedup_cross_source_occurrences`.
    """
    try:
        memo = _LIVE_EVENTS_MEMO.setdefault(db, {})
    except TypeError:  # a non-weakref-able test double — skip memoization
        memo = {}
    memo_key = (window_start, window_end)
    if memo_key in memo:
        return memo[memo_key]
    stmt = select(Event).where(
        Event.status == "live",
        or_(
            Event.date.between(window_start, window_end),
            Event.rrule.isnot(None),
            Event.rdate.isnot(None),
        ),
    )
    candidates = list(db.scalars(stmt).unique().all())
    # Movie showtimes (tagged "movie", category_slug="movies") have their own
    # surface at /movies and the home "At the movies today" strip. One theater
    # emits ~200 showtime rows/day, so keep them out of the general events feed
    # (/events-ui Today, the home "Happening today" module, the week strip).
    candidates = [c for c in candidates if "movie" not in (c.tags or [])]

    pairs: list[tuple[Event, date]] = []
    seen: set[tuple[Any, date]] = set()

    def _emit(ev: Event, occ_date: date) -> None:
        key = (ev.id, occ_date)
        if key in seen:
            return
        seen.add(key)
        pairs.append((ev, occ_date))

    scheduled = [c for c in candidates if c.rrule or c.rdate]
    for ev, occ_date in occurrences_in_window(
        scheduled, window_start=window_start, window_end=window_end
    ):
        _emit(ev, occ_date)

    for ev in candidates:
        if ev.date is not None and window_start <= ev.date <= window_end:
            _emit(ev, ev.date)

    by_day: dict[date, list[Event]] = {}
    for ev, occ_date in dedup_cross_source_occurrences(pairs):
        by_day.setdefault(occ_date, []).append(ev)
    memo[memo_key] = by_day
    return by_day


def real_happenings_by_day(
    db: Session, *, window_start: date, window_end: date
) -> dict[date, int]:
    """Per-day count of REAL dated happenings — the canonical "N events on day X"
    number (F6/F9).

    A happening is an Event-table occurrence: a one-off event *or* a recurring
    EVENT landing on that day (a weekly concert, the farmers market). It excludes
    the three things that made every surface's count disagree and made far-future
    days read falsely "busy":

    * **venue class-schedule rosters** (entity ``Schedule`` rows — the ~55 gym
      classes that project onto *every* day; counted separately as classes),
    * **movie showtimes** (already excluded by :func:`_live_events_by_day`), and
    * **always-open venue hours** (never Event rows).

    The result is honest and day-varying — a quiet far-future day reads ~10, not
    ~95 — and stable across reloads (no ``now`` filtering, so a fixed day's number
    doesn't drift as events end). One bulk query for the whole window (reuses
    :func:`_live_events_by_day`), so a strip or month grid stays cheap.
    """
    return {
        d: len(evs)
        for d, evs in _live_events_by_day(
            db, window_start=window_start, window_end=window_end
        ).items()
    }

# ---------------------------------------------------------------------------
# Explore strips — driven by the live A.3 taxonomy departments
# ---------------------------------------------------------------------------
#
# The 15 level-0 departments ARE the category nav (2026-06-09 rewire; the old
# lumped CATEGORY_FILTERS buckets are retired and 301 away). Labels and counts
# come from the live Category tree via ``leaf_pages.all_departments`` — one
# grouped query — so a renamed department or a newly gate-clearing leaf shows
# up here without touching this file. A department absent from the DB (or
# with no gate-clearing leaf) is omitted: honest omission, never a dead link.




_SERVICE_DEPARTMENT_SLUGS: tuple[str, ...] = (
    "home-and-property-services",
    "auto-rv-and-marine",
    "beauty-and-personal-care",
    "pets",
    "professional-and-financial",
    "city-and-government",
)










_TIER_CSS = {
    _TIER_SPECIAL: "special",
    _TIER_MUSIC: "music",
    _TIER_COMMUNITY: "community",
    _TIER_WATER: "water",
    _TIER_OTHER: "community",
    _TIER_AQUATIC: "class",
    _TIER_CLASS: "class",
}

_SPECIAL_HINTS = (
    "festival", "fest", "parade", "derby", "tournament", "poker run", "balloon",
    "boat show", "fireworks", "rodeo", "grand prix", "london bridge days",
    "concert series", "car show", "expo", "championship", "celebration",
)
# Civic/government detection (the "Board of Adjustment Meeting" must not fall
# through to the music tier — the old substring matcher saw "dj" inside
# "aDJustment") now lives in :mod:`app.home.event_buckets` as ``is_civic`` so the
# events-page bucket routing and this tier classifier share one keyword list.
# Lake / "On the water" hints — activities literally on Lake Havasu or the
# Bridgewater Channel. Pool words ("swim", "aqua", "pool") are deliberately NOT
# here: they live in _AQUATIC_HINTS and route to the Aquatic Center group. The
# bare-"swim"/"swimming" that used to live here sent the Aquatic Center's "Open
# Swim" to "On the water" (the live bug this split fixes).
_WEEK_WATER_HINTS = (
    "lake", "kayak", "boat", "paddle", "paddling",
    "channel", "regatta", "jet ski", "wakeboard", "sail", "fishing", "fish",
    "marina", "river",
)
# Aquatic Center / POOL activities — these happen in the pool, never on the
# lake, so they must not tier or color as "On the water". Checked before the
# class and water hints so "Open Swim", "Family Swim", "Lap Swim", "Aqua Zumba"
# and "Water Aerobics" all route to the Aquatic Center group. Genuine lake
# activities carry a lake word (above) and no pool word, so they fall through.
# Pool words. "splash" was dropped (2026-06-23): it is not a swim-CLASS signal
# and it swept one-off celebrations into the Fitness list ("Splash Bash! Red,
# White & Blue", "HEAT Hotel Stars, Stripes & Splashes"). Genuine pool classes
# carry "swim"/"aqua"/"water aerobics"/"lap swim", not "splash".
_AQUATIC_HINTS = (
    "swim", "swimming", "aqua", "aquatic", "pool", "dive", "diving",
    "water aerobics", "water fitness", "water exercise", "water polo", "lifeguard",
)
# On-the-water ACTIVITY words — these literally cannot happen in a lap pool, so a
# title carrying one is Lake & Boating even when an 'aquatics' source tag would
# otherwise read it as a pool class (live: "Sunrise Kayak", tagged aquatics,
# landed in Fitness & classes). Checked on the TITLE so the tag can't override.
_ONWATER_ACTIVITY_HINTS = (
    "kayak", "kayaking", "paddleboard", "paddle", "paddling", "canoe", "canoeing",
    "sail", "sailing", "regatta", "wakeboard", "jet ski", "jetski",
)
_MUSIC_HINTS = (
    "live music", "music", "band", "concert", "dj", "karaoke", "dance party",
    "nightlife", "open mic", "comedy", "comedian", "improv", "theater", "theatre",
    "stand-up", "standup", "cabaret",
)
_COMMUNITY_HINTS = (
    "market", "farmers", "art walk", "artwalk", "fair", "fundraiser", "charity",
    "library", "story time", "bingo", "potluck", "meetup", "club", "workshop",
    # Recurring venue social games — a weekly Trivia/Quiz night is a "Happening
    # today" community event, not a fitness class (without this it hit the
    # recurring→TIER_CLASS fallback below and landed in Fitness & classes).
    "trivia", "quiz night", "game night",
)
_CLASS_HINTS = (
    "aqua", "aerobics", "yoga", "pilates", "lap swim", "pickleball", "fitness",
    "lesson", "class", "zumba", "dodgeball", "bootcamp", "tai chi", "spin",
    "spinning", "water fitness", "senior", "story hour",
    # Sports route into "Fitness & sports" (the renamed classes group) — BMX
    # racing and the like are sports, not "Happening today" one-offs (Casey
    # 2026-06-24). Specific terms only (not bare "race"/"racing", which would
    # sweep in boat races / fun runs).
    "bmx", "motocross", "pump track",
)
# Food / charity-dinner novelty one-offs (a fish fry, pancake breakfast, a gator
# "feed"). Hosted at a bar/brewery, these can inherit that venue's coarse `music`
# tag and wrongly tier as Music & nightlife (live: "Troy's Alligator Feed"). They
# are "Happening today" events, not shows — the guard below demotes them UNLESS
# they carry a real live-music signal (a band/concert/curated act). Kept tight and
# unambiguous so it can never pull a genuine show out of the Music group.
_FOOD_NOVELTY_HINTS = (
    "feed", "fish fry", "cook-off", "cookoff", "chili cook",
    "pancake breakfast", "spaghetti dinner", "bake sale", "ice cream social",
)

# Hints match on WORD BOUNDARIES, not substrings. The substring matcher
# produced false tiers from letters buried inside unrelated words ("dj" in
# "adjustment", "spin" in "inspiring", "fish" in "selfish"). Each hint allows
# a plural or gerund tail ("class" → "classes", "kayak" → "kayaking") so
# boundaries don't cost us the coverage substrings gave for free. One
# deliberate exception: "fest" matches as a SUFFIX ("Oktoberfest",
# "Winterfest") — a bare left boundary would miss the compound names it
# exists to catch.
_SUFFIX_HINTS = frozenset({"fest"})


def _compile_hints(hints: tuple[str, ...]) -> "re.Pattern[str]":
    parts = []
    for h in hints:
        left = "" if h in _SUFFIX_HINTS else r"\b"
        parts.append(left + re.escape(h) + r"(?:e?s|ing)?\b")
    return re.compile("|".join(parts))


_SPECIAL_HINTS_RE = _compile_hints(_SPECIAL_HINTS)
_WEEK_WATER_HINTS_RE = _compile_hints(_WEEK_WATER_HINTS)
_AQUATIC_HINTS_RE = _compile_hints(_AQUATIC_HINTS)
_ONWATER_ACTIVITY_RE = _compile_hints(_ONWATER_ACTIVITY_HINTS)
_MUSIC_HINTS_RE = _compile_hints(_MUSIC_HINTS)
_COMMUNITY_HINTS_RE = _compile_hints(_COMMUNITY_HINTS)
_CLASS_HINTS_RE = _compile_hints(_CLASS_HINTS)
_FOOD_NOVELTY_RE = _compile_hints(_FOOD_NOVELTY_HINTS)


def _is_music_event_type(title: str, tags: list[str] | None) -> bool:
    """True when the P2 event-type classifier reads a definite live-music or
    comedy event. Local import keeps the activity_taxonomy↔event_type_tags
    module pair free of an import cycle (mirrors classify_music_subgroup)."""
    from app.events.event_type_tags import COMEDY, LIVE_MUSIC, classify_event_type

    types = classify_event_type(title=title, tags=tags, venue=None)
    return LIVE_MUSIC in types or COMEDY in types


def _event_tier(*, title: str, tags: list[str] | None, featured: bool, recurring: bool) -> int:
    """Importance tier (lower = more prominent). See the module note above."""
    joined = (title + " " + " ".join(tags or [])).lower()
    if featured or _SPECIAL_HINTS_RE.search(joined):
        return _TIER_SPECIAL
    # Civic/government events rank (and color) as COMMUNITY; the events page
    # routes them to their own "City & Government" bucket via is_civic.
    if is_civic(title, tags):
        return _TIER_COMMUNITY
    # A food/novelty one-off (fish fry, pancake breakfast, "Alligator Feed") at a
    # bar/brewery can inherit that venue's coarse `music` tag; it is a "Happening
    # today" event, not a show. Suppress the music tiers below for it UNLESS it
    # carries a real live-music signal (band/concert/curated act) — mirrors the
    # automotive guard in event_type_tags so a genuine "Blues & BBQ Concert" stays.
    from app.events.event_type_tags import is_strong_live_music

    food_novelty_guard = bool(_FOOD_NOVELTY_RE.search(title.lower())) and not is_strong_live_music(
        title, "", " ".join(tags or [])
    )
    # A durable music/comedy signal (P2 event-type classifier: curated act names,
    # strong live-music phrasing, explicit comedy) wins over an INCIDENTAL class
    # keyword in the title — e.g. "Top Goons: A First CLASS Night of Comedy"
    # otherwise matched _CLASS_HINTS ("class") and landed in Fitness & classes.
    if not food_novelty_guard and _is_music_event_type(title, tags):
        return _TIER_MUSIC
    # An on-the-water ACTIVITY in the TITLE (kayak, paddle, sail, …) is Lake &
    # Boating, even if an 'aquatics' tag would otherwise read it as a pool class —
    # you can't kayak in a lap pool. Checked before the aquatic tier and on the
    # title (not tags) so the tag can't override the activity.
    if _ONWATER_ACTIVITY_RE.search(title.lower()):
        return _TIER_WATER
    # Pool / Aquatic Center activities ("Open Swim", "Lap Swim", "Aqua Zumba",
    # "Water Aerobics") are NOT "on the water" (the lake). Routed to their own
    # Aquatic Center tier BEFORE the class + water checks so a pool session
    # never wears the lake pill and never lands in the lake group.
    if _AQUATIC_HINTS_RE.search(joined):
        return _TIER_AQUATIC
    # A class signal ("pilates", "yoga", …) is a low tier, so it must never be
    # promoted to MUSIC/WATER just because it shares a keyword. Only consider the
    # one-off tiers when there's no class signal.
    if _CLASS_HINTS_RE.search(joined):
        return _TIER_CLASS
    if not food_novelty_guard and _MUSIC_HINTS_RE.search(joined):
        return _TIER_MUSIC
    if _COMMUNITY_HINTS_RE.search(joined):
        return _TIER_COMMUNITY
    if _WEEK_WATER_HINTS_RE.search(joined):
        return _TIER_WATER
    # No keyword signal: a one-off is a real (untyped) event; a recurring block
    # reads as an ongoing class so it never outranks a one-off.
    return _TIER_CLASS if recurring else _TIER_OTHER


def _event_css_type(*, title: str, tags: list[str] | None, tier: int) -> str:
    """Display pill for a week-strip headline. Ranking and display are separate
    concerns: a "Kayak Meetup" *ranks* at the community tier (the approved
    headline order puts community above water), but it still *wears* the water
    pill — on-the-water is this town's identity category and the legend keys
    color to activity type, not headline priority."""
    if tier in (_TIER_COMMUNITY, _TIER_OTHER):
        joined = (title + " " + " ".join(tags or [])).lower()
        if _AQUATIC_HINTS_RE.search(joined):
            return "aquatic"
        if _WEEK_WATER_HINTS_RE.search(joined):
            return "water"
    return _TIER_CSS[tier]


def _short_time(t: time | None) -> str | None:
    """12-hour label; see :func:`app.events.time_labels.format_short_time`."""
    if t is None:
        return None
    return format_short_time(t)


def week_strip(
    db: Session,
    *,
    today: date,
    days: int = 7,
    per_day: int = 3,
    selected: date | None = None,
) -> dict[str, Any]:
    """Build the next-``days`` strip: a today-first calendar (Slice F).

    Only the TODAY card headlines individual one-off events — up to ``per_day``
    of them (default 3), the rest implied by the rollup. The other days collapse
    to counts only (``event_count`` / ``class_count`` / ``summary``) and carry an
    empty ``events`` list, so the template renders them as compact count cards.
    Every day still links to ``/events-ui?date=`` so nothing is more than one tap
    away.

    Mirrors ``calendar_month``'s honest-omission contract: empty days render an
    em-dash, never fabricated content. Recurring classes (recurring Event rows
    plus venue Schedule classes) never take a headline slot — they appear only in
    the ``summary`` rollup ("2 events · 14 classes"). Time-unknown one-offs (the
    midnight ingest fallback) show no time — never "12 AM" — and sort after timed
    events within their tier.
    """
    # The strip is today-anchored, EXCEPT when a far date is selected (the home
    # day-picker navigated to e.g. a month out): then center the window on the
    # selected day so it's visible and highlighted (F9 — the strip must follow
    # the selection, with a persistent "Today" anchor back, surfaced via
    # ``includes_today`` / ``today_iso``). A selection within the next ``days``
    # keeps the today-first window unchanged.
    if selected is not None and not (today <= selected <= today + timedelta(days=days - 1)):
        window_start = selected - timedelta(days=(days - 1) // 2)
    else:
        window_start = today
    end = window_start + timedelta(days=days - 1)
    by_day = _live_events_by_day(db, window_start=window_start, window_end=end)

    # Venue Schedule classes (entity Schedule rows, not events) join the per-day
    # class count so the rollup matches the day's /events-ui?date= page;
    # event-table twins (the aquatic programs) are dropped by normalized title
    # + date + start-time window, same as calendar_month.
    event_keys = {
        ((ev.title or "").strip().lower(), d, ev.start_time)
        for d, evs in by_day.items()
        for ev in evs
    }
    # Per-day category breakdown of RECURRING occurrences (recurring Event rows +
    # venue Schedule classes), bucketed by the shared definition (Slice C). One-
    # offs are the headlines / ``event_count``; this breakdown powers the home
    # events module's "Also today" rollup + per-day category lines (Phase 7). It
    # is additive — every existing field is untouched.
    def _bucket_of(*, title: str, tags: list[str] | None, featured: bool, recurring: bool) -> str:
        return _group_for_tier(
            _event_tier(title=title, tags=tags, featured=featured, recurring=recurring),
            recurring=recurring,
            title=title,
            tags=tags,
        )

    day_cat_counts: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for cat_d, cat_evs in by_day.items():
        for ev in cat_evs:
            if ev.is_recurring:
                day_cat_counts[cat_d][
                    _bucket_of(
                        title=ev.title, tags=ev.tags, featured=bool(ev.featured), recurring=True
                    )
                ] += 1

    sched_classes_by_day: dict[date, int] = {}
    for occ in feed_visible_occurrences(
        drop_event_duplicates(
            class_occurrences_in_window(
                db, window_start=window_start, window_end=end, horizon_today=today
            ),
            event_keys,
        )
    ):
        sched_classes_by_day[occ.date] = sched_classes_by_day.get(occ.date, 0) + 1
        day_cat_counts[occ.date][
            _bucket_of(title=occ.title, tags=None, featured=False, recurring=True)
        ] += 1

    def _tier(ev: Event) -> int:
        return _event_tier(
            title=ev.title,
            tags=ev.tags,
            featured=bool(ev.featured),
            recurring=bool(ev.is_recurring),
        )

    def _sort_key(ev: Event) -> tuple[int, int, time]:
        return (_tier(ev), *time_sort_key(ev.start_time, ev.end_time))

    out_days: list[dict[str, Any]] = []
    for i in range(days):
        d = window_start + timedelta(days=i)
        evs = by_day.get(d, [])
        oneoffs = sorted((ev for ev in evs if not ev.is_recurring), key=_sort_key)
        class_count = sum(1 for ev in evs if ev.is_recurring) + sched_classes_by_day.get(d, 0)
        if d == today:
            label = "Today"
        elif d == today + timedelta(days=1):
            label = "Tomorrow"
        else:
            label = d.strftime("%a")
        # Slice F: only TODAY headlines individual events; the other days are
        # rendered as counts-only cards, so they carry an empty ``events`` list.
        # When a far date is selected, today may be outside the window — then no
        # card headlines (the v4 strip renders day tiles only, not headlines).
        if d == today:
            visible = [
                {
                    "title": clean_event_title(ev.title, location_name=ev.location_name),
                    # Slice C: bucket the headline by the SAME definition the
                    # events page uses (app.home.event_buckets), so the home
                    # strip's pill color + legend match /events-ui. Headlines are
                    # one-offs, so recurring=False (recurring classes roll up).
                    "type": _group_for_tier(
                        _tier(ev), recurring=False, title=ev.title, tags=ev.tags
                    ),
                    "time": short_time_label(ev.start_time, ev.end_time),
                    # 4.2: recurrence badge — a one-off carrying an rrule/rdate
                    # (or flagged recurring) gets a cadence label; a true one-off
                    # gets None and the template omits the badge. Per-day list is
                    # unchanged (still one item per day); this only labels it.
                    "recurrence_label": event_recurrence_label(
                        ev,
                        window_start=window_start,
                        window_end=end,
                        time_label=short_time_label(ev.start_time, ev.end_time),
                    ),
                }
                for ev in oneoffs[:per_day]
            ]
            overflow = max(0, len(oneoffs) - per_day)
        else:
            visible = []
            overflow = 0
        summary_bits: list[str] = []
        if oneoffs:
            summary_bits.append(f"{len(oneoffs)} event{'' if len(oneoffs) == 1 else 's'}")
        if class_count:
            summary_bits.append(f"{class_count} class{'' if class_count == 1 else 'es'}")
        total = len(oneoffs) + class_count
        # Recurring-occurrence breakdown for this day, ordered by the shared
        # GROUP_DEFS order; only buckets with content appear (honest omission).
        cats = day_cat_counts.get(d, {})
        categories = [
            {"key": key, "label": lbl, "count": cats[key]}
            for key, lbl, _icon in GROUP_DEFS
            if cats.get(key)
        ]
        out_days.append(
            {
                "iso": d.isoformat(),
                "label": label,
                # Weekday abbreviation ("Sat", "Sun", …) for the home day-picker
                # tiles, which label every day by weekday (FIX_DAYPICKER item 1)
                # rather than the Today/Tomorrow ``label`` used elsewhere.
                "dow": d.strftime("%a"),
                "md": f"{d.month}/{d.day}",
                "is_today": d == today,
                "events": visible,
                "overflow": overflow,
                "event_count": len(oneoffs),
                # F6/F9 canonical count: all real dated happenings that day
                # (one-off + recurring EVENTS), excluding the venue class roster
                # that otherwise makes every day read the same ~55. Honest and
                # day-varying; the strip pill + home header read this.
                "happenings": len(evs),
                "class_count": class_count,
                "categories": categories,
                "summary": " · ".join(summary_bits),
                "count": total,
                "has": total > 0,
                # v4.4 PR-7: date-strip activity marker (dots or headliner spark),
                # from the day's own total (see app.home.activity for the perf note).
                "act": strip_activity(total, d),
                "is_weekend": d.weekday() >= 5,
            }
        )
    return {
        "days": out_days,
        "has_any": any(day["has"] for day in out_days),
        # F9: when a far date shifts the window off the current week, the template
        # surfaces a persistent "Today" anchor back to ``today_iso``.
        "includes_today": window_start <= today <= end,
        "today_iso": today.isoformat(),
    }


# ---------------------------------------------------------------------------
# 4.2 — aggregate event cards: collapse a recurring event's many occurrences in
# a week/month/all-events window into ONE card carrying a recurrence_label.
# ---------------------------------------------------------------------------
#
# The data layer stores a recurring event as a single row + rrule/rdate that
# ``_live_events_by_day`` expands to one (event, date) pair per occurrence. The
# per-day views WANT that expansion (a class shows on each of its days). The
# AGGREGATE views (week summary, month list, all-events) do not: ten occurrences
# of one yoga class should read as a single "Yoga — Daily, 5–7 AM" card, not ten
# rows. This is a pure presentation/grouping pass over the read-path expansion —
# no schema change.


def recurrence_label(weekdays: set[int], time_label: str | None = None) -> str | None:
    """Human recurrence label for an aggregated event card, or ``None``.

    Reuses :func:`app.events.series.schedule_label` for the cadence ("Daily",
    "Mon–Fri", "Weekends", "Tue–Thu", "Mon, Wed, Fri") so the home strip, the
    events feed, and these aggregate cards all phrase recurrence identically.
    Appends the time span when known, e.g. "Daily, 5–7 AM" / "Mon–Fri, 9 AM".
    Returns ``None`` for a non-recurring occurrence (empty/single weekday set and
    no recurrence) so callers leave the field off a one-off card (the contract:
    ``recurrence_label`` is ``str | None``)."""
    cadence = _schedule_label(set(weekdays)) if weekdays else ""
    if not cadence:
        return None
    if time_label:
        return f"{cadence}, {time_label}"
    return cadence


def event_recurrence_label(
    ev: Event, *, window_start: date, window_end: date, time_label: str | None = None
) -> str | None:
    """Recurrence label for a single Event row on a per-day surface, or ``None``.

    Used to populate the recurrence badge on the LIVE week-view headline
    (``d.headline.recurrence_label``) and the home today-card items
    (``ev.recurrence_label``) WITHOUT collapsing the per-day lists: the event
    still shows once on its day, this only adds a cadence label when the row is
    genuinely recurring.

    An event is "recurring" when it carries an ``rrule``/``rdate`` schedule or is
    flagged ``is_recurring``. The weekday set is derived from the event's own
    occurrence dates inside ``[window_start, window_end]`` (via
    :func:`app.events.recurrence.expand_event`), then phrased by
    :func:`recurrence_label`. A one-off (no schedule, not flagged) yields
    ``None``. Defensive: a malformed/over-cap rrule never raises here — it falls
    back to ``None`` so a bad row can't break the page.
    """
    has_schedule = bool(getattr(ev, "rrule", None) or getattr(ev, "rdate", None))
    if not (has_schedule or bool(getattr(ev, "is_recurring", False))):
        return None
    weekdays: set[int] = set()
    try:
        for occ_date in expand_event(
            ev, window_start=window_start, window_end=window_end
        ):
            weekdays.add(occ_date.weekday())
    except Exception:  # pragma: no cover - never break the page on a bad rrule
        weekdays = set()
    # Flagged-recurring rows with no expandable schedule in this window (a
    # materialised single instance) still read as recurring — anchor the cadence
    # on the event's own stored weekday so the badge is never empty for them.
    if not weekdays and ev.date is not None:
        weekdays = {ev.date.weekday()}
    return recurrence_label(weekdays, time_label)





def _event_pill_type(title: str, tags: list[str] | None, *, featured: bool) -> str:
    """Month-cell pill color. Reuses the shared tier classifier so it can never
    disagree with the rest of the calendar — a pool event reads 'aquatic', a
    lake event 'water', etc. (A separate keyword list drifted: it missed
    multi-word pool phrases like 'water aerobics', so 'Water Aerobics' tiered
    AQUATIC but the month pill said 'class'.)"""
    tier = _event_tier(title=title or "", tags=tags, featured=featured, recurring=False)
    return _event_css_type(title=title or "", tags=tags, tier=tier)


def _pill_sort_key(pill: dict[str, Any]) -> tuple[int, int, int]:
    """Order pills so one-offs/specials win the 2 visible slots (DL-16).

    Recurring classes sink to the bottom so they fall into the "+N" overflow
    count rather than crowding out a one-off festival. A recurring-in-PRACTICE
    series row (``series`` — see :func:`calendar_month`) sinks below genuine
    one-offs the same way, EXCEPT when it tiers special, so a real multi-day
    festival/tournament keeps its slot while a nightly venue promo doesn't.
    """
    ptype = pill.get("type")
    type_rank = {"special": 0, "water": 1, "aquatic": 2, "class": 3}.get(ptype, 1)
    recurring_rank = 1 if pill.get("recurring") else 0
    series_rank = 1 if (pill.get("series") and ptype != "special") else 0
    return (recurring_rank, series_rank, type_rank)


#: A one-off title seen on at least this many distinct days of one month is a
#: de-facto recurring series for pill ranking (a weekly venue night hits 4-5
#: days, a nightly promo ~30; a genuine one-off or 2-day event never trips it).
_SERIES_MIN_DAYS = 3


def _is_venue_hours_row(tags: list[str] | None) -> bool:
    """True for a DB venue-hours line (``facet:hours`` — "Indoor Golf
    Simulators", the funzone/golf all-day hours rows). A place being open is
    not an event: the day view renders hours from the curated registries and
    filters these DB twins (see app.home.events_views); the month grid has no
    hours concept at all, so they never become cell pills or counts."""
    return any(str(t).strip().lower() == "facet:hours" for t in (tags or []))


def calendar_month(
    db: Session, *, year: int, month: int, today: date, family: bool = False,
    seniors: bool = False,
) -> dict[str, Any]:
    """Build a month grid of real events. Empty days stay empty (no fabrication).

    Each in-month cell carries an ISO date (``iso``) so the template can link
    every day to ``/events-ui?date=``. Only one-off events take the two visible
    pill slots and the cell ``count``; recurring classes (recurring Event rows
    plus venue Schedule classes) collapse into ``class_count`` — rendered as a
    small "N classes" badge — instead of flooding the cell ("+44").

    ``family=True`` / ``seniors=True`` (the /events-ui audience toggles) keep only
    kid/family or senior occurrences — same :func:`is_family_event` /
    :func:`is_senior_event` heuristics the day and week views use, so all three
    zooms agree. ``family`` wins if both are passed.
    """
    from app.events.family_filter import is_family_event
    from app.events.senior_filter import is_senior_event

    if family:
        seniors = False
    first_weekday, days_in_month = _calendar.monthrange(year, month)
    # Python's monthrange: Monday=0. The grid leads with Sunday, so shift.
    lead_blanks = (first_weekday + 1) % 7

    occ_by_date = _live_events_by_day(
        db,
        window_start=date(year, month, 1),
        window_end=date(year, month, days_in_month),
    )
    if family:
        occ_by_date = {
            d: [ev for ev in evs if is_family_event(ev.title, ev.tags, ev.location_name)]
            for d, evs in occ_by_date.items()
        }
    elif seniors:
        occ_by_date = {
            d: [ev for ev in evs if is_senior_event(ev.title, ev.tags, ev.location_name)]
            for d, evs in occ_by_date.items()
        }
    by_day: dict[int, list[dict[str, Any]]] = {}
    event_keys: set[tuple[str, date, time | None]] = set()
    from app.events.event_type_tags import is_civic_meeting

    # Recurring-in-practice series (2026-07-01 month audit): venue specials
    # published as distinct dated ONE-OFF rows (Family Night Golf, Cosmic
    # Bowling, Glow in the Park, Junior Jump Time) carry is_recurring=False on
    # every row, so each day's copy claimed a visible pill slot and the month
    # read as the same few venue promos repeated 31 times. A normalized title
    # occurring on >= _SERIES_MIN_DAYS distinct days this month is flagged
    # ``series`` so the pill sort demotes it below genuine one-offs — it keeps
    # its cell count and still surfaces on days with nothing else on.
    series_days: dict[str, set[date]] = {}
    for occ_date, evs in occ_by_date.items():
        for ev in evs:
            if ev.is_recurring or _is_venue_hours_row(ev.tags):
                continue
            _key = (ev.title or "").strip().lower()
            if _key:
                series_days.setdefault(_key, set()).add(occ_date)
    series_titles = {t for t, d in series_days.items() if len(d) >= _SERIES_MIN_DAYS}

    for occ_date, evs in occ_by_date.items():
        bucket = by_day.setdefault(occ_date.day, [])
        for ev in evs:
            event_keys.add(((ev.title or "").strip().lower(), occ_date, ev.start_time))
            # Venue-hours rows (facet:hours) are places being OPEN, not events
            # (2026-07-01 month audit): never a month-cell pill or count. The
            # day view already filters these DB twins of the curated registries.
            if _is_venue_hours_row(ev.tags):
                continue
            # Government meetings (City Council, Board of Adjustment…) are not
            # leisure plans (2026-07-01 audit A3): keep them off the month
            # cells' pills/counts. The day view still lists them under its own
            # "Local Government" group.
            if is_civic_meeting(ev.title, getattr(ev, "description", None), ev.location_name):
                continue
            bucket.append(
                {
                    "title": clean_event_title(ev.title, location_name=ev.location_name),
                    "type": _event_pill_type(
                        ev.title or "", ev.tags, featured=bool(ev.featured)
                    ),
                    "recurring": bool(ev.is_recurring),
                    # De-facto recurring series (see above): sorts after genuine
                    # one-offs in the visible pill slots.
                    "series": (ev.title or "").strip().lower() in series_titles,
                    # Per-event start time for the v4 calendar chips (Casey
                    # 2026-06-29: show the time on the chip, not a color square).
                    # None for time-TBD events so the chip shows just the title.
                    "time": short_time_label(ev.start_time, ev.end_time),
                }
            )

    # Venue class schedules (Schedule rows on entities) are not events; union
    # them in so a "Mon-Thu BJJ" venue shows on every class day. They count as
    # recurring class pills, so they feed the "+N" overflow, never the two
    # visible one-off slots. Aquatic-style duplicates (classes that are ALSO
    # recurring events) are dropped by normalized title + date + time window.
    class_occs = feed_visible_occurrences(
        drop_event_duplicates(
            class_occurrences_in_window(
                db,
                window_start=date(year, month, 1),
                window_end=date(year, month, days_in_month),
                horizon_today=today,
            ),
            event_keys,
        )
    )
    for occ in class_occs:
        if family and not is_family_event(occ.title, None, occ.venue):
            continue
        if seniors and not is_senior_event(occ.title, None, occ.venue):
            continue
        by_day.setdefault(occ.date.day, []).append(
            {"title": clean_event_title(occ.title), "type": "class", "recurring": True}
        )

    cells: list[dict[str, Any]] = [{"in_month": False} for _ in range(lead_blanks)]
    # 1.1: month-wide rollups for the calendar header ("12 events · 88 classes
    # this month"). Summed from the same per-cell figures the grid renders, so
    # the header can never disagree with the cells below it.
    month_oneoff_total = 0
    month_class_total = 0
    for day in range(1, days_in_month + 1):
        evs = by_day.get(day, [])
        # Only one-offs claim the two visible pill slots (and the cell count);
        # recurring classes collapse into the "N classes" badge.
        oneoffs = sorted((e for e in evs if not e.get("recurring")), key=_pill_sort_key)
        class_count = sum(1 for e in evs if e.get("recurring"))
        month_oneoff_total += len(oneoffs)
        month_class_total += class_count
        cells.append(
            {
                "in_month": True,
                "day": day,
                "iso": date(year, month, day).isoformat(),
                "is_today": (year == today.year and month == today.month and day == today.day),
                "events": oneoffs[:2],
                "overflow": max(0, len(oneoffs) - 2),
                "count": len(oneoffs),
                "class_count": class_count,
                "has": bool(evs),
                "special": any(e.get("type") == "special" for e in oneoffs),
            }
        )
    while len(cells) % 7 != 0:
        cells.append({"in_month": False})

    weeks = [cells[i : i + 7] for i in range(0, len(cells), 7)]

    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    return {
        "label": f"{_calendar.month_name[month]} {year}",
        "weeks": weeks,
        "has_any": bool(by_day),
        "prev": f"{prev_year:04d}-{prev_month:02d}",
        "next": f"{next_year:04d}-{next_month:02d}",
        # 1.1: month totals for the calendar header (sums of the per-cell
        # one-off ``count`` and ``class_count``).
        "month_oneoff_total": month_oneoff_total,
        "month_class_total": month_class_total,
    }


def parse_cal_param(value: str | None, *, default: datetime) -> tuple[int, int]:
    """Parse a ``?cal=YYYY-MM`` param, falling back to the current month."""
    if value:
        try:
            year_s, month_s = value.split("-", 1)
            year, month = int(year_s), int(month_s)
            if 1 <= month <= 12 and 2000 <= year <= 2100:
                return year, month
        except (ValueError, AttributeError):
            pass
    return default.year, default.month


# ---------------------------------------------------------------------------
# Featured row — real sponsors or the honest "claim this spot" empty state
# ---------------------------------------------------------------------------




def _tile(emoji: str, title: str, blurb: str, url: str) -> dict[str, str]:
    return {"emoji": emoji, "label": title, "blurb": blurb, "url": url}


# The mode-landing config now serves ONLY /night — WS10 gave /lake, /family and
# /seniors their own routes/templates with real content (and /night its own
# night_redesign.html). The night hero copy + drink tiles live here; the rest of
# /night's content is assembled in redesign.py + the route.

def _night_tiles() -> list[dict[str, str]]:
    # Both drink tiles land on the bars-and-breweries LEAF (a real filtered list),
    # not the unfiltered Eat & Drink department (audit, mode pages #3).
    #
    # WS10: the old chat deep-link tiles are gone — /night now renders REAL,
    # server-rendered content instead (no /chat?q= tiles anywhere on the hub):
    #   * "Live Music" / "Happy Hours" tiles → live music renders as an events
    #     list (redesign.night_music_rows, the "music" bucket for tonight) and
    #     happy hours as an honest "coming soon" card (redesign.NIGHT_COMING_SOON);
    #   * "Late Kitchens" → the venues-open-past-10 PM list (late_night_kitchens);
    #   * "Get Home Safe" → dropped (no structured taxi/rideshare surface exists).
    bars = "/categories/eat-and-drink/bars-and-breweries"
    return [
        _tile("🍸", "Bars & Lounges", "Waterfront, dive, cocktail", bars),
        _tile("🍺", "Breweries & Wineries", "Tastings, taprooms", bars),
    ]


# WS10 (2026-07-08): /family got its own hub (app.home.family_hub +
# family_redesign.html), so its mode-landing config + chat-deflection tiles are
# gone. Only /night remains a mode landing.
_MODE_CONFIG: dict[str, dict[str, Any]] = {
    "night": {
        "eyebrow": "Night",
        "heading": "Where the night goes",
        "blurb": (
            "The bars and patios, tonight's live music, and the kitchens still "
            "serving late."
        ),
        "sec_head": "Out tonight",
        "tiles": _night_tiles,
    },
}



def mode_landing(db: Session, mode: str) -> dict[str, Any]:
    """Assemble a mode-landing context.

    ``mini_conditions`` is populated for Lake only (live conditions); Night and
    Family have no honest live hero metric yet, so their hero shows copy only —
    the mock counters are deliberately absent (anti-confabulation, §4.10).
    """
    if mode not in _MODE_CONFIG:
        raise KeyError(mode)
    cfg = _MODE_CONFIG[mode]
    return {
        "mode": mode,
        "eyebrow": cfg["eyebrow"],
        "heading": cfg["heading"],
        "blurb": cfg["blurb"],
        "sec_head": cfg["sec_head"],
        "tiles": cfg["tiles"](),
        "mini_conditions": [],
    }
