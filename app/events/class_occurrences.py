"""Expand venue class Schedules into calendar occurrences (read-time bridge).

The captured gym/class schedules live as recurring ``Schedule`` rows on venue
Entities (published by ``scripts/import_captured_schedules.py``) -- NOT as
``Event`` rows. They render on ``/provider/<slug>`` pages, but the home month
calendar and ``/events-ui`` read the events table only, so a "Mon-Thu BJJ"
venue looked empty on the calendar. This module is the read-time bridge: it
expands recurring Schedule rows into dated occurrences so the calendar views
can union them in, without double-writing class data into the events table.

Dedup contract: some venues' classes exist BOTH as events (the parks-rec
aquatic programs are ingested as recurring Events) and as captured Schedule
rows. Callers pass the (lowercased title, date) keys of the event occurrences
they already have; matching class occurrences are dropped so "Lap Swim" never
shows twice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time, timedelta

from sqlalchemy.orm import Session

from app.db.models import Category, Entity, EntityCategory, Provider, Schedule
from app.events.activity_taxonomy import provider_activity_label
from app.events.dedup_match import (
    DEFAULT_DEDUP_TIME_WINDOW_MINUTES,
    times_within_window,
    tokens_subset_match,
)

_DAY_TO_INT = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

# Curated website links for page-less class venues — real businesses with class
# schedules on the calendar but NO directory Provider row, so their rows had no
# link. Per Casey's 2026-06-23 call: don't unpublish a venue that has a legit web
# presence — point users to its real site instead. Keyed by Entity.slug; used
# ONLY as a fallback when the venue has no provider website (a future real
# Provider listing wins automatically, so this self-deactivates). Verified live
# 2026-06-23. The durable fix is a directory listing; this is the render-time
# bridge the brief prefers (fixes current + future scrapes from these venues).
_PAGELESS_VENUE_WEBSITES: dict[str, str] = {
    "havasu-pilates-studio": "https://havasupilates.com/",
    "desert-bloom-learning-center": "https://www.desertbloomlearningcenter.com/",
    # "havasu-horseback-rides" removed (two-surface spec §6, Casey 2026-06-25):
    # the Pony / Lead Line Rides occurrences carry no usable info, so they are
    # pulled off both calendar surfaces. The Entity's Schedule rows are
    # deactivated at the data layer (gated prod-data op) so the occurrences stop
    # expanding entirely.
}

_ANCHOR_SLUG_RE = re.compile(r"[^a-z0-9]+")


def program_anchor(title: str, venue: str | None) -> str:
    """Stable ``#program-…`` anchor id for a permalink-less recurring program.

    A class series with no published provider page (e.g. the "Pony / Lead Line
    Rides" horseback program) has no permalink, so the home feed used to fall
    back to ``/events-ui?date=…`` — the whole day's list, not the row the user
    tapped. This gives that exact row an id on /events-ui so the feed can
    deep-link straight to it (``#program-…``). Deterministic from title+venue so
    the link and the row id always agree.
    """
    base = _ANCHOR_SLUG_RE.sub("-", f"{title} {venue or ''}".lower()).strip("-")
    return f"program-{base}" if base else "program"

# Safety valve: the calendar asks for at most a month; never expand more.
_MAX_WINDOW_DAYS = 62

# F6/F9 (2026-06-30): how far past *today* a captured recurring class roster is
# trusted to still hold. The Schedule rows carry no end date, so without a cap
# "Mon BJJ" projects onto every Monday forever — making a day eight months out
# read ~90 "happenings" that are really the same speculative roster. Beyond this
# horizon the calendar shows only real dated events; within it, classes render as
# today. Six weeks balances "browsing next month still shows classes" against
# "don't claim a gym schedule we can't vouch for." Tunable. Callers opt in by
# passing ``horizon_today`` (the real current date); a None anchor disables the
# cap (used by the Places & Ongoing roster view and by tests).
CLASS_PROJECTION_HORIZON_DAYS = 42


@dataclass(frozen=True)
class ClassOccurrence:
    title: str
    date: date
    start_time: time | None
    end_time: time | None
    venue: str
    provider_slug: str | None
    weekdays: frozenset[int]  # Mon=0 .. Sun=6 -- the series' full pattern
    # Provider-derived activity label (Yoga / Dance / Gymnastics / …) for classes
    # whose title carries no activity keyword, so they leave "Other classes" by
    # inheriting their studio's discipline. None when no provider signal exists.
    provider_activity: str | None = None
    # The venue provider's external website, used as the link fallback when there
    # is no published directory page (no slug). None when the venue has neither.
    provider_website: str | None = None

    @property
    def url(self) -> str:
        """The row's link target, preferring the internal directory page.

        Resolution order (brief 2026-06-23 "every program row must resolve to a
        working link"): (1) the venue's ``/provider/<slug>`` directory page;
        (2) the provider's external website when there is no directory page;
        (3) empty string, and the template renders an honest non-link row (the
        old ``/events-ui`` fallback made every slugless class a self-link dead
        end — live: all Havasu Pilates rows linked back to the page they were on).
        """
        if self.provider_slug:
            return f"/provider/{self.provider_slug}"
        if self.provider_website:
            return self.provider_website
        return ""

    @property
    def anchor(self) -> str:
        """``#program-…`` row id for the permalink-less case (see
        :func:`program_anchor`). Used by the home feed to deep-link this exact
        program on /events-ui instead of the whole-day list."""
        return program_anchor(self.title, self.venue)


def class_occurrences_in_window(
    db: Session,
    *,
    window_start: date,
    window_end: date,
    horizon_today: date | None = None,
) -> list[ClassOccurrence]:
    """All recurring-Schedule class occurrences in the inclusive date window.

    ``horizon_today`` (the real current date) caps the projection at
    ``today + CLASS_PROJECTION_HORIZON_DAYS`` so the calendar surfaces stop
    showing the indefinitely-recurring class roster on far-future days (F6/F9).
    Pass None to disable the cap (the Places & Ongoing roster view, tests)."""
    if window_end < window_start:
        return []
    window_end = min(window_end, window_start + timedelta(days=_MAX_WINDOW_DAYS))
    if horizon_today is not None:
        window_end = min(
            window_end, horizon_today + timedelta(days=CLASS_PROJECTION_HORIZON_DAYS)
        )
    if window_end < window_start:
        return []

    rows = (
        db.query(Schedule, Entity, Provider)
        .join(Entity, Schedule.entity_id == Entity.id)
        .outerjoin(Provider, Provider.entity_id == Entity.id)
        .filter(
            Schedule.schedule_type == "recurring",
            Schedule.days_of_week.isnot(None),
            Entity.is_active.is_(True),
        )
        .all()
    )

    # Bulk-load each venue Entity's directory category slugs once, so a class
    # whose title has no activity keyword can inherit its provider's discipline
    # (e.g. "Elementary B" at a 'dance-studios' entity → Dance) without an N+1.
    entity_ids = {ent.id for _s, ent, _p in rows if ent is not None}
    cats_by_entity: dict[str, list[str]] = {}
    if entity_ids:
        for ent_id, slug in (
            db.query(EntityCategory.entity_id, Category.slug)
            .join(Category, Category.id == EntityCategory.category_id)
            .filter(EntityCategory.entity_id.in_(entity_ids))
            .all()
        ):
            cats_by_entity.setdefault(ent_id, []).append(slug)

    out: list[ClassOccurrence] = []
    for sched, ent, prov in rows:
        title = (sched.notes or "").strip()
        if not title:
            continue  # untitled rows are junk on the venue page too
        weekdays = frozenset(
            _DAY_TO_INT[d.lower()]
            for d in (sched.days_of_week or [])
            if isinstance(d, str) and d.lower() in _DAY_TO_INT
        )
        if not weekdays:
            continue
        if prov is not None and prov.is_active is False:
            prov = None
        venue = (ent.name or "").strip()
        slug = prov.slug if prov is not None else None
        website = prov.website if prov is not None else None
        if not website:
            # Page-less venue with a known real site → link there (curated).
            website = _PAGELESS_VENUE_WEBSITES.get(ent.slug)
        # Provider-derived activity + youth signal (drains "Other classes" and
        # routes youth programs to Kids & Family). The provider's NAME + its
        # directory subcategory/EntityCategory slugs feed the classifier.
        cat_slugs = list(cats_by_entity.get(ent.id, []))
        if prov is not None:
            for extra in (prov.subcategory, prov.primary_category, prov.category):
                if extra:
                    cat_slugs.append(extra)
        prov_activity = provider_activity_label(
            prov.provider_name if prov is not None else ent.name, cat_slugs
        )
        # Seasonal window (2026-07-03): honour an explicit start_date/end_date so a
        # season-limited schedule (e.g. summer "Open Swim", June–July) stops
        # rendering once it ends instead of projecting forever. Both are nullable;
        # a NULL bound means "unbounded" (every existing class row is NULL/NULL,
        # so this is inert for them). Clamp the iteration to the season.
        lo = max(window_start, sched.start_date) if sched.start_date else window_start
        hi = min(window_end, sched.end_date) if sched.end_date else window_end
        d = lo
        while d <= hi:
            if d.weekday() in weekdays:
                out.append(
                    ClassOccurrence(
                        title=title,
                        date=d,
                        start_time=sched.start_time,
                        end_time=sched.end_time,
                        venue=venue,
                        provider_slug=slug,
                        weekdays=weekdays,
                        provider_activity=prov_activity,
                        provider_website=website,
                    )
                )
            d += timedelta(days=1)
    out.sort(key=lambda o: (o.date, o.start_time or time(0, 0), o.venue, o.title))
    # Collapse duplicate Schedule rows for the same venue/slot before any
    # caller sees them (the doubled Havasu Pilates capture — see
    # _drop_schedule_twins). Sorted input keeps the survivor deterministic.
    return _drop_schedule_twins(out)


# --------------------------------------------------------------------------- #
# Dedup matching (2026-06-10): the exact (title, date) contract let every
# slightly-renamed twin through — the parks-rec Event says "Motion & Mobility
# Margie" while the captured Schedule says "Motion & Mobility"; "Tai Chi Vince"
# vs "Tai Chi (Aquatic)"; "Lap Swim" vs "Lap Swim (Morning)". All six aquatic
# slots rendered twice on the live /events-ui. Titles are now reduced to a
# token set (parentheticals, time-of-day tokens, and weekday tokens stripped)
# and a class occurrence is a duplicate when one side's tokens are a subset of
# the other's AND the start times agree within a window — so "Lap Swim
# (Evening)" at 5 PM survives a 5 AM "Lap Swim" Event row.
# --------------------------------------------------------------------------- #

#: Start-time tolerance for treating same-titled rows as one occurrence.
#: The shared default (also backs app.events.dedup's env-tunable ingest window).
DEDUP_TIME_WINDOW_MINUTES = DEFAULT_DEDUP_TIME_WINDOW_MINUTES

_PAREN_RE = re.compile(r"\([^)]*\)")
_TIME_TOKEN_RE = re.compile(
    r"\b\d{1,2}(?::\d{2})?\s*(?:-|–|to)\s*\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?\b"
    r"|\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b",
    re.IGNORECASE,
)
_DAY_TOKEN_RE = re.compile(
    r"\b(?:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)(?:day)?s?\b", re.IGNORECASE
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _dedup_title_tokens(title: str) -> frozenset[str]:
    """Reduce a class/event title to comparable tokens.

    Drops parentheticals ("(Wed/Fri)", "(Morning)", "(155)"), clock tokens
    ("9:00 AM", "4-5:30pm"), and weekday tokens — the disambiguators the two
    ingest paths disagree on — then splits on non-alphanumerics.
    """
    t = (title or "").lower()
    t = _PAREN_RE.sub(" ", t)
    t = _TIME_TOKEN_RE.sub(" ", t)
    t = _DAY_TOKEN_RE.sub(" ", t)
    return frozenset(tok for tok in _NON_ALNUM_RE.split(t) if tok)


def _times_compatible(
    a: time | None, b: time | None, *, window_minutes: int = DEDUP_TIME_WINDOW_MINUTES
) -> bool:
    """True when two start times plausibly describe the same occurrence.

    A missing time on either side is a wildcard (the old contract matched on
    title+date alone, and TBD-time Event rows must still suppress their
    Schedule twin).
    """
    return times_within_window(a, b, window_minutes=window_minutes, missing_is_wildcard=True)


def _tokens_match(a: frozenset[str], b: frozenset[str]) -> bool:
    return tokens_subset_match(a, b)


def drop_event_duplicates(
    occurrences: list[ClassOccurrence],
    event_keys: set[tuple[str, date]] | set[tuple[str, date, time | None]],
) -> list[ClassOccurrence]:
    """Drop class occurrences already represented by a live Event occurrence.

    ``event_keys`` accepts the legacy ``(lowercased title, date)`` pairs or the
    richer ``(title, date, start_time)`` triples; with triples, the start-time
    window keeps distinct sessions of the same class apart. Matching is
    token-subset on normalized titles (see :func:`_dedup_title_tokens`), so
    instructor-suffixed Event titles still suppress their Schedule twins.
    """
    by_date: dict[date, list[tuple[frozenset[str], time | None]]] = {}
    for key in event_keys:
        title, day = key[0], key[1]
        start = key[2] if len(key) > 2 else None  # type: ignore[misc]
        by_date.setdefault(day, []).append((_dedup_title_tokens(title), start))

    kept: list[ClassOccurrence] = []
    for o in occurrences:
        tokens = _dedup_title_tokens(o.title)
        is_dup = any(
            _tokens_match(tokens, ev_tokens) and _times_compatible(o.start_time, ev_start)
            for ev_tokens, ev_start in by_date.get(o.date, ())
        )
        if not is_dup:
            kept.append(o)
    return kept


# ── public-feed visibility (Casey 2026-07-10) ─────────────────────────────────
# Internal governance — a board / executive / council / commission meeting — is
# not "what's on" content; it belongs in the org's policy log, not the calendar.
_GOVERNANCE_MEETING_RE = re.compile(
    r"\b(?:executive\s+(?:board|session|committee)|board\s+(?:meeting|of\s+directors)|"
    r"(?:city\s+)?council\s+meeting|commission\s+meeting|committee\s+meeting)\b",
    re.IGNORECASE,
)


def is_governance_meeting(title: str | None) -> bool:
    """True for an internal governance meeting (board/executive/council/commission)
    — suppressed from public feeds."""
    return bool(title and _GOVERNANCE_MEETING_RE.search(title))


def feed_visible_occurrences(occurrences: list[ClassOccurrence]) -> list[ClassOccurrence]:
    """Render-level rule for public feeds: NO unlinked plain-text rows. Keep only
    occurrences that resolve to a working link (a ``/provider`` page or the venue's
    website — :attr:`ClassOccurrence.url`), and drop internal governance meetings
    outright. A slugless, website-less program is suppressed until the org claims
    its listing — never rendered as a dead-end plain-text row. (The venue's OWN
    roster page is a different surface and does not use this filter.)"""
    return [o for o in occurrences if o.url and not is_governance_meeting(o.title)]


def _leading_words(title: str) -> list[str]:
    return [w for w in _NON_ALNUM_RE.split((title or "").lower()) if w]


def _shares_leading_stem(a: str, b: str, *, min_words: int = 2) -> bool:
    """True when two titles share a >= ``min_words`` leading word stem.

    The WS5 §14.2 series/instance signal: "Afternoon Enrichment Workshops" and
    "Afternoon Enrichment: Creative Arts Studio" share the stem "afternoon
    enrichment" but diverge after it, so neither is a token-subset of the other.
    A one-word coincidence ("Yoga Beginner" vs "Yoga Advanced") does NOT pair."""
    wa, wb = _leading_words(a), _leading_words(b)
    shared = 0
    for x, y in zip(wa, wb):
        if x != y:
            break
        shared += 1
    return shared >= min_words


def _drop_schedule_twins(occurrences: list[ClassOccurrence]) -> list[ClassOccurrence]:
    """Collapse duplicate Schedule rows for the same venue/slot.

    The captured-schedule import stored some classes twice with title variants
    ("9:00 AM Beginner Pilates (Wed/Fri)" AND "Beginner Reformer Pilates -
    9:00 AM Wed/Fri" — every Havasu Pilates slot doubled on live /events-ui).
    Within one (date, venue), rows whose normalized tokens are subset-related
    and whose times sit inside the dedup window collapse to one; the row with
    MORE tokens (more specific title) wins, ties keep the first by sort order.
    The underlying Schedule rows still need a data cleanup — this is the
    render-time guard.
    """
    kept: list[ClassOccurrence] = []
    by_group: dict[tuple[date, str], list[tuple[frozenset[str], ClassOccurrence, int]]] = {}
    for o in occurrences:
        group = by_group.setdefault((o.date, o.venue.strip().lower()), [])
        tokens = _dedup_title_tokens(o.title)
        replaced = False
        for i, (k_tokens, k_occ, k_idx) in enumerate(group):
            # Exact-slot over-capture: identical start+end+weekdays is one class
            # no matter how the title is worded (a venue can't run two DIFFERENT
            # classes in the same room at the same time). Collapse as long as the
            # titles share an activity word, so a genuine two-room "Yoga"+"Spin"
            # at the same time (no shared token) is NOT merged. This catches the
            # Havasu Pilates capture stored 4-5x per slot under title variants.
            same_slot = (
                o.start_time == k_occ.start_time
                and o.end_time == k_occ.end_time
                and frozenset(o.weekdays) == frozenset(k_occ.weekdays)
            )
            if same_slot and (tokens & k_tokens):
                pass  # exact-slot twin
            elif not (
                _tokens_match(tokens, k_tokens)
                # Series + its own instance share a title STEM (WS5 §14.2):
                # "Afternoon Enrichment Workshops" vs "Afternoon Enrichment:
                # Creative Arts Studio" — neither is a token-subset, but the shared
                # 2-word stem plus the time-window check below make them one row.
                or _shares_leading_stem(o.title, k_occ.title)
            ):
                continue
            # Within-venue twins must agree on a REAL time window (no
            # wildcard): "Adult No-Gi (Morning)" and "(Night)" share tokens
            # and may only differ by clock.
            elif o.start_time is None or k_occ.start_time is None:
                if o.start_time is not k_occ.start_time:
                    continue
                if frozenset(o.weekdays) != frozenset(k_occ.weekdays):
                    continue
            elif not _times_compatible(o.start_time, k_occ.start_time):
                continue
            # Twin found: keep the more specific (more tokens), else first-in.
            if len(tokens) > len(k_tokens):
                kept[k_idx] = o
                group[i] = (tokens, o, k_idx)
            replaced = True
            break
        if not replaced:
            group.append((tokens, o, len(kept)))
            kept.append(o)
    return kept
