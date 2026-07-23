"""Multi-source event dedup + venue resolution + merge semantics (Phase 9b)."""

from __future__ import annotations

import functools
import os
import re
from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rapidfuzz import fuzz, process
from sqlalchemy import false, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from app.db.models import Entity, Event, Provider
from app.events.dedup_match import (
    DEFAULT_DEDUP_TIME_WINDOW_MINUTES,
    GENERIC_TITLE_QUALIFIERS,
    start_minutes,
    times_within_window,
    tokens_subset_match,
)
from app.events.scrapers.base import EventPayload, normalize_event_title
from app.events.time_labels import is_time_tbd

DEDUP_DATETIME_WINDOW_MINUTES = int(
    os.environ.get("EVENT_DEDUP_DATETIME_WINDOW_MINUTES", str(DEFAULT_DEDUP_TIME_WINDOW_MINUTES))
)
DEDUP_TITLE_FUZZY_THRESHOLD = int(os.environ.get("EVENT_DEDUP_TITLE_THRESHOLD", "85"))

# Catalog-scan normalization cache. resolve_venue_entity_id re-normalizes the
# SAME ~3k entity names / provider addresses on every call (once per event in a
# scrape batch). normalize_event_title is pure (regex over the input string),
# so a string-keyed cache is safe; scoped to this module's scan loops so
# unbounded one-off inputs (raw titles, descriptions) don't churn it.
_norm_cached = functools.lru_cache(maxsize=8192)(normalize_event_title)

# --------------------------------------------------------------------------- #
# Canonical-URL identity (cross-source dedup: go_lake_havasu + river_scene_import)
# --------------------------------------------------------------------------- #
# Tracking params that must never participate in a canonical identity (mirrors the
# ingest-time strip in the go_lake_havasu scraper).
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAM_EXACT = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid"})

# A Facebook event URL carries a stable global event id -- the strongest cross-
# source identity we have (the same FB event is routinely surfaced by both
# go_lake_havasu's organizer link and a river_scene_import "Facebook" label).
_FB_EVENT_ID_RE = re.compile(r"facebook\.com/events/(\d+)", re.IGNORECASE)


def _strip_tracking_query(query: str) -> str:
    kept = [
        (k, v)
        for k, v in parse_qsl(query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAM_EXACT
        and not any(k.lower().startswith(p) for p in _TRACKING_PARAM_PREFIXES)
    ]
    return urlencode(kept)


def canonical_event_identity(url: str | None) -> str | None:
    """Return a canonical identity key for an event URL, or ``None``.

    Two ingest sources (go_lake_havasu organizer links, river_scene_import
    "Website"/"Facebook" labels) frequently point at the *same* real event. We
    collapse them by deriving a stable key:

    * a Facebook event URL -> ``"fb:<event_id>"`` (the global FB event id);
    * any other URL -> ``"url:<scheme-stripped host+path+clean-query>"`` with the
      scheme dropped, host lowercased, ``www.`` removed, trailing slash trimmed,
      fragment dropped, and tracking params (fbclid/UTM) removed.

    Returns ``None`` for empty / unparseable input so callers can skip it.
    """
    if not url:
        return None
    s = str(url).strip()
    if not s:
        return None
    fb = _FB_EVENT_ID_RE.search(s)
    if fb:
        return f"fb:{fb.group(1)}"
    if "://" not in s:
        s = "https://" + s.lstrip("/")
    parts = urlsplit(s)
    host = (parts.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return None
    path = (parts.path or "").rstrip("/")
    query = _strip_tracking_query(parts.query) if parts.query else ""
    cleaned = urlunsplit(("", host, path, query, ""))  # scheme+fragment dropped
    cleaned = cleaned.lstrip("/")
    return f"url:{cleaned.lower()}" if cleaned else None



# --------------------------------------------------------------------------- #
# Recurring-series instance dedupe (venue + title + weekday)
# --------------------------------------------------------------------------- #
def recurring_series_key(
    venue_name: str | None,
    title: str | None,
    weekday: int | None,
) -> tuple[str, str, int] | None:
    """Natural key for one weekday-instance of a recurring series.

    ``(normalized venue, normalized title, weekday)`` -- the tuple that identifies
    a single occurrence of e.g. "Farmers Market @ Visitor Center, every Saturday".
    Returns ``None`` when venue/title/weekday is missing (no usable key).
    """
    v = normalize_event_title(venue_name or "")
    t = normalize_event_title(title or "")
    if not v or not t or weekday is None:
        return None
    return (v, t, weekday)



def find_duplicate(
    db: Session,
    *,
    venue_entity_id: str | None,
    start_date: date,
    start_time_obj: time | None,
    normalized_title: str,
) -> Event | None:
    """Return existing Event row if a likely duplicate, else None."""
    stmt = select(Event).where(Event.date == start_date)
    if venue_entity_id:
        prov_ids = list(
            db.scalars(select(Provider.id).where(Provider.entity_id == venue_entity_id)).all()
        )
        clauses = [Event.entity_id == venue_entity_id]
        if prov_ids:
            clauses.append(Event.provider_id.in_(prov_ids))
        stmt = stmt.where(or_(*clauses) if clauses else false())
    candidates = list(db.scalars(stmt).all())
    norm = normalize_event_title(normalized_title)

    # A bare-noon (12:00, no end) placeholder some aggregators emit is really a
    # "time unknown", so it must merge onto a really-timed twin regardless of the
    # ±window — otherwise the noon placeholder and the real 9 PM event (Jul 4
    # fireworks) both survive ingest. Treat either side being TBD/bare-noon as
    # time-agnostic.
    incoming_tbd = _start_is_tbd_for_dedup(start_time_obj, None)

    def _within_window(cand: Event) -> bool:
        # Either side TBD/bare-noon is time-agnostic → always in window. Candidates
        # all share ``start_date`` (query filter), so the ±window on the start
        # times is the same test the old datetime-seconds diff computed; a missing
        # time on either side is a wildcard (the pre-shared-matcher contract).
        if incoming_tbd or _start_is_tbd_for_dedup(cand.start_time, cand.end_time):
            return True
        return times_within_window(
            start_time_obj,
            cand.start_time,
            window_minutes=DEDUP_DATETIME_WINDOW_MINUTES,
            missing_is_wildcard=True,
        )

    # T3.1 fast path: most duplicates are *exact* normalized-title matches
    # (same scraper, same source). One dict build replaces a token_sort_ratio
    # call per candidate; the fuzzy loop below stays as the fallback for
    # near-miss titles.
    by_norm: dict[str, list[Event]] = {}
    for cand in candidates:
        by_norm.setdefault(
            normalize_event_title(cand.normalized_title or cand.title), []
        ).append(cand)
    for cand in by_norm.get(norm, ()):
        if _within_window(cand):
            return cand

    for cand in candidates:
        if (
            fuzz.token_sort_ratio(
                normalize_event_title(cand.normalized_title or cand.title),
                norm,
            )
            < DEDUP_TITLE_FUZZY_THRESHOLD
        ):
            continue
        if _within_window(cand):
            return cand
    return None


def resolve_venue_entity_id(
    db: Session,
    venue_name: str | None,
    venue_address: str | None = None,
) -> str | None:
    """Match venue name to an existing Entity id when confidence is high.

    Perf shape (this runs once per event payload on the ingest path): the
    previous implementation hydrated every active Entity as a full ORM object
    and ran a Python-loop ``token_sort_ratio`` per row (~165-215ms/call at
    3.2k entities). Now: column-only ``(id, name)`` scan, an exact
    normalized-name probe first (re-scraped venue strings repeat verbatim, and
    an exact match is a 100-score that nothing can beat), and the fuzzy
    fallback via ``process.extractOne`` (C loop, same scorer/first-max-wins
    semantics as the old Python loop). The address tier likewise scans
    ``(entity_id, address)`` tuples only.
    """
    name = (venue_name or "").strip()
    if not name:
        return None
    norm = normalize_event_title(name)
    rows = db.execute(select(Entity.id, Entity.name).where(Entity.is_active.is_(True))).all()
    ids: list[str] = []
    normed: list[str] = []
    for eid, ename in rows:
        n = _norm_cached(ename or "")
        if n == norm:
            return eid
        ids.append(eid)
        normed.append(n)
    hit = process.extractOne(norm, normed, scorer=fuzz.token_sort_ratio, score_cutoff=90)
    if hit is not None:
        return ids[hit[2]]
    if venue_address:
        addr_norm = normalize_event_title(venue_address)
        prov_rows = db.execute(
            select(Provider.entity_id, Provider.address).where(
                Provider.is_active.is_(True), Provider.entity_id.is_not(None)
            )
        ).all()
        for ent_id, addr in prov_rows:
            pa = _norm_cached(addr or "")
            if pa and fuzz.partial_ratio(addr_norm, pa) >= 85:
                return ent_id
    return None


# --------------------------------------------------------------------------- #
# Render-time cross-source dedup (display paths only; never writes the DB)
# --------------------------------------------------------------------------- #
# Two scrape sources routinely carry the SAME real-world event with cosmetic
# differences the ingest-time matchers above miss: one source stores the street
# address as the venue and fabricates a noon start ("Lake Havasu Farmers Market"
# at "2144 McCulloch Blvd N ..." 12:00 PM), the other has the named venue and
# the real 8:00 AM time; titles can differ only by a curly apostrophe ("Lady
# Lee's" vs "Lady Lee's"). These helpers collapse such twins at render time --
# grouped by (normalized title, occurrence date), one survivor per group -- so
# every display surface that opts in (home week strip, month calendar,
# /events-ui buckets and day view) shows the event once. Read-only by design:
# the rows stay in the DB untouched for ingest reconciliation and admin review.

# Two events with the same title but REAL start times further apart than this
# are legitimately separate sessions (matinee vs evening) -- never merged.
_SEPARATE_SESSION_GAP_MINUTES = 120


def _render_title_key(event: Event) -> str:
    """Title key: lowercased, punctuation/curly quotes stripped, spaces collapsed."""
    return normalize_event_title(event.normalized_title or event.title or "")


def _start_is_tbd_for_dedup(start_time: time | None, end_time: time | None) -> bool:
    """Time-TBD for dedup purposes: the shared midnight-fallback contract
    (:func:`app.events.time_labels.is_time_tbd`) PLUS the bare-noon fabrication
    some aggregator sources emit instead of midnight. A noon start with a real
    end time is a real noon event; only the bare 12:00-with-no-end is suspect.
    Display labels are untouched -- this widens TBD only inside a duplicate
    group, where a bare-noon twin should lose to its really-timed sibling."""
    if is_time_tbd(start_time, end_time):
        return True
    if start_time is None:
        return False
    # Bare-noon fabrication: a noon start with no end time.
    if start_time.hour == 12 and start_time.minute == 0 and end_time is None:
        return True
    # Deep pre-dawn (01:00–04:59) with no end time is almost always an aggregator
    # AM/PM parse error (the live "Troy's Alligator Feed" parsed a 3 PM event as
    # 3 AM), so it reads as TBD and loses to a real daytime twin inside its
    # duplicate group. 05:00+ is left alone — early classes (5 AM Lap Swim) are
    # real. Guarded on no-end-time so a genuine timed pre-dawn block is untouched.
    if 1 <= start_time.hour <= 4 and end_time is None:
        return True
    return False


def _venue_is_named_place(venue: str | None) -> bool:
    """A named place ("Go Lake Havasu Visitor Center") vs a bare street address
    ("2144 McCulloch Blvd N ..."): contains letters and doesn't start with a
    digit. Heuristic, used only to rank survivors inside a duplicate group."""
    v = (venue or "").strip()
    return bool(v) and any(c.isalpha() for c in v) and not v[0].isdigit()


def location_has_street_address(name: str | None) -> bool:
    """The location string begins with a street number ("3100 Sweetwater Ave")."""
    return bool(re.match(r"\s*\d+\s+\S", name or ""))


def is_bare_venue(name: str | None) -> bool:
    """A low-information venue: a single bare word like "Calvary" with no street
    address — the organizer/campus name stood in for a real location. A multi-word
    named place ("Go Lake Havasu Visitor Center") is NOT bare, so it is never
    downgraded to a raw address."""
    s = (name or "").strip()
    if not s or location_has_street_address(s):
        return False
    return len(re.findall(r"[A-Za-z]+", s)) <= 1


def _source_priority(source: str | None) -> int:
    """Min EVENT_SOURCE_PRIORITY across the comma-separated provenance string.

    Imported lazily: :mod:`app.contrib.event_reconciler` imports this module at
    its top level, so a module-level import here would be circular.
    """
    from app.contrib.event_reconciler import EVENT_SOURCE_PRIORITY

    parts = [p.strip() for p in (source or "").split(",") if p.strip()]
    if not parts:
        return 99
    return min(EVENT_SOURCE_PRIORITY.get(p, 99) for p in parts)


def _has_flyer(event: Event) -> bool:
    """The row carries a flyer/poster image URL."""
    return bool((getattr(event, "image_url", None) or "").strip())


def _survivor_rank(event: Event) -> tuple[bool, bool, int, bool, int, str]:
    """Sort key for picking ONE survivor in a duplicate cluster (lowest wins):
    real start time > named venue > source priority > has flyer > longer
    description > id.

    Source priority outranks the flyer/description tiebreaks so an authoritative
    row (e.g. a curated ``admin`` entry) wins over a longer aggregator blurb,
    even when the aggregator carries the richer text. Among rows of equal source
    priority a flyer-bearing twin wins so the poster survives; the survivor also
    ABSORBS a dropped twin's flyer/richer text/real time (see
    ``_absorb_display_fields``), so the tiebreak only decides which row's *other*
    fields (venue, url) anchor the merged display. See ``EVENT_SOURCE_PRIORITY``.
    """
    return (
        _start_is_tbd_for_dedup(event.start_time, event.end_time),
        not _venue_is_named_place(event.location_name),
        _source_priority(event.source),
        not _has_flyer(event),
        -len((event.description or "").strip()),
        str(event.id),
    )


def _absorb_longest_description(survivor: Event, losers: list[Event]) -> None:
    """Graft the longest description among the cluster onto the survivor — unless
    the survivor is an authoritative (operator / source-priority-0) row that
    already carries its own curated text, which must never be replaced by a
    longer aggregator blurb (the swim-card rule)."""
    current = (survivor.description or "").strip()
    authoritative = bool(getattr(survivor, "operator_override", False)) or _source_priority(
        survivor.source
    ) == 0
    if authoritative and current:
        return
    best = survivor.description or ""
    best_len = len(current)
    for lo in losers:
        d = lo.description or ""
        if len(d.strip()) > best_len:
            best, best_len = d, len(d.strip())
    if best != (survivor.description or ""):
        set_committed_value(survivor, "description", best)


def _absorb_display_fields(survivor: Event, losers: list[Event]) -> None:
    """Make the render survivor ABSORB the best display fields from its dropped
    twin(s): a flyer image, the longest description, and a real start time over a
    TBD/fabricated one — so the single rendered row carries them even when they
    lived on a twin that lost the survivor sort (§3B).

    Uses :func:`sqlalchemy.orm.attributes.set_committed_value`, which sets the
    value as if freshly loaded from the DB (no dirty flag), so this stays purely
    read-only: the render paths that call the dedup never write these grafts back
    to the database (autoflush won't emit an UPDATE for a committed value)."""
    # Flyer: gap-fill only (a survivor that already has an image keeps its own).
    if not _has_flyer(survivor):
        for lo in losers:
            if _has_flyer(lo):
                set_committed_value(survivor, "image_url", lo.image_url)
                break
    # Real start time over a TBD/fake one: only when the survivor itself is TBD
    # (the sort already prefers a real-timed survivor, so this is a safety net for
    # clusters where the survivor was chosen on another axis).
    if _start_is_tbd_for_dedup(survivor.start_time, survivor.end_time):
        for lo in losers:
            if not _start_is_tbd_for_dedup(lo.start_time, lo.end_time):
                set_committed_value(survivor, "start_time", lo.start_time)
                set_committed_value(survivor, "end_time", lo.end_time)
                break
    # More-specific LOCATION: a bare one-word venue ("Calvary") absorbs a twin's
    # street address ("3100 Sweetwater Ave"), which is more useful for directions.
    # Guarded to a bare survivor so a real named venue ("Go Lake Havasu Visitor
    # Center") is never downgraded to a raw address twin (§3.1).
    if is_bare_venue(survivor.location_name):
        for lo in losers:
            if location_has_street_address(lo.location_name):
                set_committed_value(survivor, "location_name", lo.location_name)
                lo_norm = getattr(lo, "location_normalized", None)
                if lo_norm:
                    set_committed_value(survivor, "location_normalized", lo_norm)
                break
    _absorb_longest_description(survivor, losers)


def _cluster_survivor_and_losers(
    cluster: list[tuple[int, Event]],
    *,
    core_positions: set[int] | None = None,
) -> tuple[int, list[int]]:
    """(survivor position, [loser positions]) for one already-formed cluster.

    ``core_positions`` restricts who may WIN survivorship (used by
    :func:`_group_clusters` so a folded pre-dawn misparse twin can never anchor
    the merged display on source priority alone); every member outside the
    winner still drops as a loser. ``None`` → any member may win.
    """
    pool = cluster
    if core_positions:
        pool = [m for m in cluster if m[0] in core_positions] or cluster
    survivor = min(pool, key=lambda m: _survivor_rank(m[1]))[0]
    losers = [idx for idx, _ev in cluster if idx != survivor]
    return survivor, losers


def _group_clusters(members: list[tuple[int, Event]]) -> list[tuple[int, list[int]]]:
    """One group's clusters as (survivor position, [loser positions]) pairs.

    Timed (non-TBD) members are clustered by start-time proximity: starts within
    :data:`_SEPARATE_SESSION_GAP_MINUTES` of the previous one chain into the same
    cluster; a bigger gap means a genuinely separate session, so each cluster
    keeps its own survivor (the matinee/evening guard). Time-TBD members are
    duplicates of a timed sibling when one exists (the fake-noon twin loses);
    a pre-dawn (01:00–04:59) member is demoted into the same fold when a
    daytime (>= 05:00) sibling exists — even when it carries an end time (the
    AM/PM window-misparse twin); with no timed sibling TBD members all collapse
    onto a single TBD survivor. The caller drops the losers and grafts their
    best fields onto the survivor.
    """
    timed = [
        m for m in members if not _start_is_tbd_for_dedup(m[1].start_time, m[1].end_time)
    ]
    if not timed:
        # All TBD → one survivor absorbs the whole group.
        return [_cluster_survivor_and_losers(members)]
    # Pre-dawn demotion (2026-07-22): _start_is_tbd_for_dedup already reads a
    # bare 01:00–04:59 start with NO end time as an AM/PM parse error, but the
    # live escape was a misparse that shifted the whole WINDOW ("3–5 PM" scraped
    # as "3–5 AM") — its end time defeats the per-event guard, and Troy's
    # Alligator Feed rendered at both 3 AM and 3 PM on 2026-07-25. Inside a
    # duplicate group, a pre-dawn start coexisting with a real daytime
    # (>= 05:00) sibling is that misparse twin regardless of end time: fold it
    # like a TBD member (it drops; its fields absorb onto the daytime survivor).
    # A group whose timed members are ALL pre-dawn is left alone, so an
    # overnight event two sources agree on still renders; 05:00+ stays real
    # (5 AM Lap Swim). The per-event contract — a LONE timed pre-dawn block is
    # real (pinned in test_calendar_classification) — is unchanged; this
    # verdict needs the group context.
    demoted: list[tuple[int, Event]] = []
    if any(m[1].start_time.hour >= 5 for m in timed):
        demoted = [m for m in timed if 1 <= m[1].start_time.hour <= 4]
    if demoted:
        demoted_positions = {pos for pos, _ev in demoted}
        timed = [m for m in timed if m[0] not in demoted_positions]
    timed.sort(key=lambda m: start_minutes(m[1].start_time))
    clusters: list[list[tuple[int, Event]]] = [[timed[0]]]
    for member in timed[1:]:
        gap = start_minutes(member[1].start_time) - start_minutes(clusters[-1][-1][1].start_time)
        if gap <= _SEPARATE_SESSION_GAP_MINUTES:
            clusters[-1].append(member)
        else:
            clusters.append([member])
    # TBD members are twins of the nearest timed cluster's survivor when one
    # exists — fold them (and any demoted pre-dawn twin) into the first cluster
    # so their fields can be absorbed (and they drop) rather than surviving as a
    # separate timeless/misparsed row. Survivorship of that cluster is
    # restricted to its real timed core: a demoted twin must never win on
    # source priority and anchor the merged display at 3 AM.
    tbd = [m for m in members if _start_is_tbd_for_dedup(m[1].start_time, m[1].end_time)]
    folded = tbd + demoted
    if not folded:
        return [_cluster_survivor_and_losers(c) for c in clusters]
    first_core = {pos for pos, _ev in clusters[0]}
    clusters[0].extend(folded)
    out = [_cluster_survivor_and_losers(clusters[0], core_positions=first_core)]
    out.extend(_cluster_survivor_and_losers(c) for c in clusters[1:])
    return out


def _group_survivor_positions(members: list[tuple[int, Event]]) -> set[int]:
    """Positions that survive one group (survivors only). Thin wrapper over
    :func:`_group_clusters` for callers/tests that need just the survivor set, not
    the survivor→losers mapping used by the field-absorb."""
    return {survivor for survivor, _losers in _group_clusters(members)}


# --------------------------------------------------------------------------- #
# Second pass: cross-source SAME-SESSION twins under DIFFERENT titles
# --------------------------------------------------------------------------- #
# The title-keyed pass groups by (title, date), so one real session surfaced by
# multiple sources under DIFFERENT titles -- the Aquatic Center "Free Family Swim"
# (admin) / "Free Swim Day!" (go_lake_havasu) / "Open Swim" (allevents) triple --
# never collapses. This tight second pass merges two events ONLY when ALL hold:
#   1. DIFFERENT sources (same-source distinct sessions never merge),
#   2. both at a SPECIFIC venue (not the bare-city fallback) that token-set match,
#   3. one title's significant words are a SUBSET of the other's, AND
#   4. their time windows overlap (or, when an end time is missing, starts within
#      _CROSS_SOURCE_START_GAP_MINUTES).
# Guards (2)+(3) were added after a live run of the bare "overlap + different
# source" rule over-merged DISTINCT events that merely share a container venue
# ("Mini Bakers" vs "Sports Camp" at Parks & Rec) or an activity word at an
# activity venue ("Cosmic Bowling" vs a charity "… Bowl" night at Havasu Lanes).
# With all four guards, exactly the swim triple collapses across the live set;
# the 63-cluster prevalence run (dominated by same-source clusters) is untouched.
# Venue ENTITY resolution does NOT converge for the real variants ("Aquatic
# Center" vs "Lake Havasu City Aquatic Center" resolve to different entities), so
# the venue check is a token-set match on the names rather than a resolved id.
_CROSS_SOURCE_START_GAP_MINUTES = 90
_VENUE_MATCH_RATIO = 92

# A bare-city venue ("Lake Havasu City") is the no-real-venue fallback and is NOT
# a session, so it must never anchor a same-session merge. (Generic *container*
# venues like "Lake Havasu City Parks & Recreation" pass the venue check but are
# held apart by the title-token guard below — distinct programs share the building
# but not a significant title word.)
_BARE_CITY_VENUES: frozenset[str] = frozenset({"lake havasu city", "lake havasu", "havasu"})
# Title words too generic to imply "same session" — the merge needs a SHARED word
# OUTSIDE this set (so "Free Family Swim"/"Open Swim"/"Free Swim Day!" share
# "swim", but "Mini Bakers" and "Sports Camp" at one Parks&Rec venue share
# nothing). The list itself lives in dedup_match (2026-07-22) so the
# class-occurrence qualifier guard strips the SAME words.
_TITLE_STOPWORDS: frozenset[str] = GENERIC_TITLE_QUALIFIERS


def _significant_title_tokens(ev: Event) -> set[str]:
    """Title tokens >= 4 chars that are not generic stopwords — the words that
    actually name the activity ("swim", "yoga", "bingo")."""
    norm = _norm_cached(ev.normalized_title or ev.title or "")
    return {w for w in norm.split() if len(w) >= 4 and w not in _TITLE_STOPWORDS}


def _titles_share_activity(a: Event, b: Event) -> bool:
    """One title's significant words are a SUBSET of the other's (both non-empty).

    A subset — not a mere intersection — is the tight signal for "same session,
    different title": "Open Swim" {swim} ⊆ "Free Family Swim …" {swim, …}, and
    "Free Swim Day!" {swim} ⊆ it too, so the cross-source swim triple collapses.
    But two DISTINCTLY-named events that merely share the venue's activity word —
    "Cosmic Bowling" {cosmic, bowling} vs "… Humane Society … Bowl" — are neither a
    subset of the other, so they stay separate (the over-merge the bare-token rule
    produced)."""
    return tokens_subset_match(_significant_title_tokens(a), _significant_title_tokens(b))


def _is_specific_venue(ev: Event) -> bool:
    """The venue is a real named place, not the bare-city no-venue fallback."""
    norm = _norm_cached(ev.location_name or "")
    return bool(norm) and norm not in _BARE_CITY_VENUES


def _venue_match(a: Event, b: Event) -> bool:
    """Two events read as the SAME venue: equal normalized names, or a token-set
    ratio >= _VENUE_MATCH_RATIO ("aquatic center" ⊆ "lake havasu city aquatic
    center" → 100). Tiny names must match exactly (no fuzzy on <5 chars)."""
    na = _norm_cached(a.location_name or "")
    nb = _norm_cached(b.location_name or "")
    if not na or not nb:
        return False
    if na == nb:
        return True
    if len(na) < 5 or len(nb) < 5:
        return False
    return fuzz.token_set_ratio(na, nb) >= _VENUE_MATCH_RATIO


def _times_overlap_for_merge(a: Event, b: Event) -> bool:
    """Time windows overlap; or, when EITHER end time is missing, the starts are
    within _CROSS_SOURCE_START_GAP_MINUTES. A missing start never overlaps."""
    sa, sb = a.start_time, b.start_time
    if sa is None or sb is None:
        return False
    if a.end_time is not None and b.end_time is not None:
        return (
            start_minutes(sa) < start_minutes(b.end_time)
            and start_minutes(sb) < start_minutes(a.end_time)
        )
    return abs(start_minutes(sa) - start_minutes(sb)) <= _CROSS_SOURCE_START_GAP_MINUTES


def _different_source(a: Event, b: Event) -> bool:
    """The two rows carry different (non-empty) source strings."""
    sa = (a.source or "").strip().lower()
    sb = (b.source or "").strip().lower()
    return bool(sa) and bool(sb) and sa != sb


def _exact_same_start(a: Event, b: Event) -> bool:
    """Both rows carry a real start time and it is the SAME clock time."""
    return a.start_time is not None and b.start_time is not None and a.start_time == b.start_time


def _cross_source_same_session(a: Event, b: Event) -> bool:
    """Two rows are the SAME real cross-source session under different titles.

    The strict shape (all four guards): different sources, both a specific venue
    that token-match, one title's significant words subset the other's, and their
    time windows overlap.

    Calvary relaxation (§3B, 2026-07-04): the strict venue *name* match is too
    strict when two feeds describe one event with unrelated venue strings — the
    river_scene "Calvary Baptist Church (Sweetwater Campus)" at the street address
    vs the go_lake "Family Water Night at Calvary" at "Calvary". So we ALSO merge
    when the titles subset-match AND both start at the EXACT same clock time AND
    the sources differ, dropping only the ``_venue_match`` requirement. Both venues
    must still be specific (the bare-city fallback never anchors a merge), and the
    exact-time + subset-title agreement keeps this tight against the over-merge the
    venue guard was added to prevent."""
    if not (_different_source(a, b) and _is_specific_venue(a) and _is_specific_venue(b)):
        return False
    if not _titles_share_activity(a, b):
        return False
    strict = _venue_match(a, b) and _times_overlap_for_merge(a, b)
    relaxed = _exact_same_start(a, b)
    return strict or relaxed


def _uf_find(parent: dict[int, int], x: int) -> int:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _cross_source_session_clusters(
    occurrences: Sequence[tuple[Event, date]], already_dropped: set[int]
) -> list[tuple[int, list[int]]]:
    """Cross-source same-session second pass as (survivor, [loser]) clusters.

    Union-find over each date's still-surviving rows; an edge is drawn by
    :func:`_cross_source_same_session`. Each multi-row component yields one
    survivor and its losers so the caller can drop the losers and absorb their
    best display fields onto the survivor."""
    by_date: dict[date, list[tuple[int, Event]]] = {}
    for idx, (ev, occ_date) in enumerate(occurrences):
        if idx in already_dropped:
            continue
        by_date.setdefault(occ_date, []).append((idx, ev))

    clusters: list[tuple[int, list[int]]] = []
    for members in by_date.values():
        if len(members) < 2:
            continue
        parent: dict[int, int] = {idx: idx for idx, _ev in members}
        for i in range(len(members)):
            ia, ea = members[i]
            for j in range(i + 1, len(members)):
                ib, eb = members[j]
                if _cross_source_same_session(ea, eb):
                    parent[_uf_find(parent, ia)] = _uf_find(parent, ib)
        comps: dict[int, list[tuple[int, Event]]] = {}
        for idx, ev in members:
            comps.setdefault(_uf_find(parent, idx), []).append((idx, ev))
        for comp in comps.values():
            if len(comp) < 2:
                continue
            clusters.append(_cluster_survivor_and_losers(comp))
    return clusters


def dedup_cross_source_occurrences(
    occurrences: Sequence[tuple[Event, date]],
) -> list[tuple[Event, date]]:
    """Collapse cross-source duplicates of the same occurrence.

    Two passes: (1) the title-keyed pass groups by (normalized title, date) and
    keeps one survivor per group; (2) the cross-source same-session pass collapses
    DIFFERENT-titled twins of one real session at the same venue/date/time from
    different sources (see ``_cross_source_session_drops``).

    Input/output are ``(event, occurrence_date)`` pairs; survivors keep their
    input order. Untitled rows never group. Pure + read-only: callers on the
    display read paths filter what they render, nothing is written.
    """
    groups: dict[tuple[str, date], list[tuple[int, Event]]] = {}
    for idx, (ev, occ_date) in enumerate(occurrences):
        key = _render_title_key(ev)
        if key:
            groups.setdefault((key, occ_date), []).append((idx, ev))

    dropped: set[int] = set()

    def _collapse(survivor: int, losers: list[int]) -> None:
        # Drop the losers and graft their best display fields onto the survivor
        # so the one rendered row carries the flyer / richest text / real time.
        if not losers:
            return
        dropped.update(losers)
        _absorb_display_fields(occurrences[survivor][0], [occurrences[i][0] for i in losers])

    # Pass 1: same (normalized title, date) groups. Grafts first so a pass-1
    # survivor that pass 2 then merges carries its absorbed fields forward.
    for members in groups.values():
        if len(members) < 2:
            continue
        for survivor, losers in _group_clusters(members):
            _collapse(survivor, losers)
    # Pass 2: cross-source same-session twins under different titles.
    for survivor, losers in _cross_source_session_clusters(occurrences, dropped):
        _collapse(survivor, losers)
    return [pair for idx, pair in enumerate(occurrences) if idx not in dropped]


def dedup_cross_source_event_rows(rows: Sequence[Event]) -> list[Event]:
    """Row-shaped wrapper over :func:`dedup_cross_source_occurrences` for read
    paths that work with plain Event rows (each row dated by ``Event.date``)."""
    return [ev for ev, _d in dedup_cross_source_occurrences([(ev, ev.date) for ev in rows])]


def merge_scraper_into_event(
    db: Session,
    event: Event,
    payload: EventPayload,
    *,
    scrape_source: str,
) -> list[str]:
    """Apply §6.4 merge semantics; return list of field names updated."""
    updated: list[str] = []
    # Aware UTC: ``scraped_at`` is a TZAwareDateTime column, which REJECTS naive
    # datetimes on write. The old ``.replace(tzinfo=None)`` made every call here
    # raise ValueError the moment it reached ``event.scraped_at = now`` — the
    # museum-events importer (scripts/scrape_events.py) is the only caller and
    # died on its first same-title merge.
    now = datetime.now(UTC)

    def _set(attr: str, value: Any) -> None:
        if value is None or value == "":
            return
        current = getattr(event, attr, None)
        if event.operator_override and current not in (None, "", [], {}):
            return
        if current == value:
            return
        setattr(event, attr, value)
        updated.append(attr)

    _set("description", (payload.description or "").strip())
    _set("event_url", (payload.event_url or "").strip())
    if payload.venue_name and not event.location_name:
        _set("location_name", payload.venue_name.strip())
        _set("location_normalized", payload.venue_name.lower().strip())
    if payload.tags:
        existing = list(event.tags or [])
        merged = sorted(set(existing + list(payload.tags)))
        if merged != existing:
            event.tags = merged
            updated.append("tags")

    event.scraped_at = now
    event.source = scrape_source
    if updated:
        db.add(event)
    return updated
