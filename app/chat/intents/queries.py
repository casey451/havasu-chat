"""Query templates for resolved intents (Ask Hava intent catalog, Phase 1).

Each ``run_query`` dispatch turns a ``ResolvedIntent`` into a ``QueryResult``
against the REAL models -- no fabricated fields. Empty results are returned
honestly (``rows == []``); the runtime renders the "/contribute" nudge.

Rows are emitted in the **tier2 row-dict shape** so the existing component
builders (``app.chat.component_builders``) can render real cards
(``business_list`` for providers, ``day_agenda`` / ``week_strip`` for events)
without a parallel card format.

Grounding cheat-sheet (see app/chat/intents/__init__.py):
* Providers: rank by ``google_rating`` / ``google_review_count``; service
  granularity via ``subcategory`` group + name tokens; ``district`` ilike.
* Events: ``app.events.queries.events_in_window`` (status='live', date+time).
* Programs: ``age_min`` / ``age_max`` overlap, ``cost`` lives here (not Event).
* Gas: ``external_conditions_cache`` source ``gas_prices_lhc``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.chat.intents import dicts
from app.chat.intents.resolver import ResolvedIntent
from app.conditions.cache import read_source
from app.conditions.constants import SOURCE_GAS
from app.core.liveness import liveness_dampener
from app.core.timezone import now_lake_havasu
from app.db.models import Category, EntityCategory, Event, Offering, Program, Provider
from app.programs.pricing import format_offering_price, format_program_price
from app.providers.queries import is_open_now

_PROVIDER_LIMIT = 12
_EVENT_LIMIT = 24


# ---------------------------------------------------------------------------
# Within-category relevance ranking (P1-1)
# ---------------------------------------------------------------------------
#
# The Tier-2 listing path returned the same per-category top-N for every query
# in a bucket ("which launch ramp", "fish from shore", "sunset cruise" all got
# the same on-water list, ordered purely by rating). P1-1 re-orders a bucket by
# how many of the query's *distinctive* terms appear in each row's searchable
# text, breaking ties with the existing rating sort. Empty ``rank_terms`` keeps
# today's exact behavior (zero regression for existing callers/tests).

# Tokens that carry no within-category signal: intent/question/filler words plus
# locality and the generic bucket words ("boat"/"water"/"spot"/"place"). Dropping
# them keeps ranking driven by what actually distinguishes rows in a bucket
# ("launch", "ramp", "fishing", "sunset", "kayak") instead of words every row or
# every query shares.
_RANK_STOP_TERMS: frozenset[str] = frozenset(
    """a an and any anywhere are around at be best buy can cheap cheapest close
    closed could do does find for from get going good great hava have help here
    hey how i id im into is it its just like list local me my near nearby need
    new now of off ok okay on open or our out place places please right show some
    something spot spots that the their them there these they this those to today
    tonight tomorrow top town up us use want we week weekend what when where which
    while who whose why will with would you your
    lake havasu city arizona az lhc
    boat boats water""".split()
)


def _derive_rank_terms(raw_query: str | None) -> frozenset[str]:
    """Distinctive lowercase terms from a raw query, for within-category ranking.

    Tokenize, then drop stop/locality/bucket words (``_RANK_STOP_TERMS``), bare
    numbers (ages/sizes/counts — "8 year old", "28-foot"), and tokens shorter
    than three characters. The remainder are the terms that distinguish one row
    in a bucket from another. Returns ``frozenset()`` for an empty/None query,
    which makes ``relevance`` a no-op and preserves the legacy sort.
    """
    if not raw_query:
        return frozenset()
    terms: set[str] = set()
    for tok in re.split(r"[^a-z0-9]+", raw_query.lower()):
        if len(tok) < 3 or tok.isdigit() or tok in _RANK_STOP_TERMS:
            continue
        terms.add(tok)
    return frozenset(terms)


def relevance(searchable: str, rank_terms: frozenset[str]) -> int:
    """Count how many distinctive query terms appear in a row's searchable text.

    Pure and substring-based (``"ramp"`` matches the leaf slug
    ``"marinas-and-launch-ramps"``); ``searchable`` is expected lowercase. Used
    as the PRIMARY sort key ahead of the rating sort, so a row that matches more
    of the query's distinctive terms outranks a higher-rated row that matches
    fewer — within the same already-filtered bucket.
    """
    if not rank_terms:
        return 0
    return sum(1 for t in rank_terms if t in searchable)


@dataclass
class QueryResult:
    intent_key: str
    kind: str  # "providers" | "events" | "programs" | "gas"
    rows: list[dict[str, Any]] = field(default_factory=list)
    category_hint: str | None = None
    lead_in: str = ""
    label: str = "businesses"  # human noun for the business_list header
    window: str | None = None  # event window token (for day_agenda vs week_strip)

    @property
    def result_count(self) -> int:
        return len(self.rows)


# ---------------------------------------------------------------------------
# Provider queries
# ---------------------------------------------------------------------------


def _provider_sort_key(p: Provider) -> tuple:
    """Rated-first, then rating desc, then review count desc (reverse=True).

    The rating term is scaled by the liveness dampener so a stale-but-once-
    popular listing sinks below fresh peers in chat business lists (bury,
    never remove). NULL liveness -> multiplier 1.0 (non-Google rows / backfill
    pending are unaffected).
    """
    return (
        p.google_rating is not None,
        (p.google_rating or 0.0)
        * liveness_dampener(getattr(p, "liveness_score", None)),
        p.google_review_count or 0,
    )


def _leaf_slugs_for_entities(
    db: Session, entity_ids: list[str]
) -> dict[str, list[str]]:
    """Batched ``entity_id -> [category slug, ...]`` for the candidate rows.

    The within-category ranking signal for several buckets lives ONLY in the
    curated taxonomy slug (e.g. ``marinas-and-launch-ramps`` carries "launch"
    and "ramp", which appear nowhere on the ``Provider`` row — not in the name,
    google categories, category, or subcategory). One ``EntityCategory`` ->
    ``Category`` join, keyed by ``entity_id``, pulls every linked slug so the
    searchable string can include it. Returns ``{}`` for an empty input.
    """
    if not entity_ids:
        return {}
    out: dict[str, list[str]] = {}
    for eid, slug in (
        db.query(EntityCategory.entity_id, Category.slug)
        .join(Category, Category.id == EntityCategory.category_id)
        .filter(EntityCategory.entity_id.in_(entity_ids))
        .all()
    ):
        if slug:
            out.setdefault(eid, []).append(slug)
    return out


def _provider_searchable(p: Provider, leaf_slugs: list[str] | tuple[str, ...]) -> str:
    """Lowercase blob of everything a query term can match a provider against:
    name, google primary/secondary categories, legacy category + subcategory,
    and the entity's taxonomy slugs (the only place "launch"/"ramp" etc. live).
    """
    parts = [
        p.provider_name or "",
        p.google_primary_category or "",
        " ".join(p.google_categories or []),
        p.category or "",
        p.subcategory or "",
        " ".join(leaf_slugs),
    ]
    return " ".join(parts).lower()


def _query_providers(
    db: Session,
    *,
    subcats: tuple[str, ...] = (),
    legacy_categories: tuple[str, ...] = (),
    name_tokens: tuple[str, ...] = (),
    exclude_name_tokens: tuple[str, ...] = (),
    exclude_google_categories: tuple[str, ...] = (),
    district: str | None = None,
    open_now: bool = False,
    rank_terms: frozenset[str] = frozenset(),
    limit: int = _PROVIDER_LIMIT,
    now: datetime | None = None,
) -> list[Provider]:
    q = db.query(Provider).filter(
        Provider.is_active.is_(True),
        Provider.draft.is_(False),
        # [ASK #8] (2026-07-01, Casey: region-tag + exclude): rows classified
        # out-of-area are already excluded from leaf pages via ``is_local``;
        # honor the same flag on the chat bucket queries so a Kingman golf
        # course or Parker casino can't ride into a Lake Havasu answer.
        # NULL/unknown is kept — never assume an un-geocoded row is far.
        Provider.is_local.isnot(False),
    )
    bucket_conds = []
    if subcats:
        bucket_conds.append(Provider.subcategory.in_(subcats))
    if legacy_categories:
        bucket_conds.append(Provider.category.in_(legacy_categories))
    if bucket_conds:
        q = q.filter(or_(*bucket_conds))

    if exclude_google_categories:
        # Drop rows whose Google primary category is a definitely-wrong type for
        # this bucket (storage / auto / RV-park rows that ride in on a broad
        # legacy tag). NULL/blank is kept -- real rows often have no Google type.
        q = q.filter(
            or_(
                Provider.google_primary_category.is_(None),
                Provider.google_primary_category.notin_(exclude_google_categories),
            )
        )

    if name_tokens:
        token_conds = []
        for tok in name_tokens:
            like = f"%{tok}%"
            token_conds.append(Provider.provider_name.ilike(like))
            token_conds.append(Provider.google_primary_category.ilike(like))
            token_conds.append(Provider.category.ilike(like))
        q = q.filter(or_(*token_conds))

    if exclude_name_tokens:
        # Drop rows whose NAME carries an excluded token. Used by boat_rental:
        # the "boat" name token also matches storage/repair yards ("Boat Storage
        # of Lake Havasu") that aren't rentals. Name-only (not category) so a
        # rental row legitimately categorized "boat_rental" is never excluded.
        for tok in exclude_name_tokens:
            q = q.filter(~Provider.provider_name.ilike(f"%{tok}%"))

    if district:
        # District is sparsely populated (Phase-0 audit: ~0% on the dev DB), so
        # treat area as a soft preference: filter by it, but fall back to the
        # un-filtered set rather than erasing all results.
        district_rows = list(q.filter(Provider.district.ilike(f"%{district}%")).all())
        rows = district_rows if district_rows else list(q.all())
    else:
        rows = list(q.all())

    if rank_terms:
        # Re-order this already-filtered bucket by within-category relevance:
        # primary key = count of distinctive query terms in the row's searchable
        # text; ties fall back to the existing rated-first/rating/reviews sort.
        slugs_by_eid = _leaf_slugs_for_entities(
            db, [p.entity_id for p in rows if p.entity_id]
        )

        def _rank_key(p: Provider) -> tuple:
            searchable = _provider_searchable(p, slugs_by_eid.get(p.entity_id, ()))
            return (relevance(searchable, rank_terms), *_provider_sort_key(p))

        rows.sort(key=_rank_key, reverse=True)
    else:
        rows.sort(key=_provider_sort_key, reverse=True)

    if open_now:
        kept: list[Provider] = []
        for p in rows:
            is_open, _ = is_open_now(p, now=now)
            if is_open is False:
                continue  # explicitly closed -> drop for an open-now ask
            kept.append(p)  # open or hours-unknown (degrade gracefully)
        rows = kept

    return rows[:limit]


def _thumb_url(p: Provider) -> str | None:
    try:
        from app.providers.photo_urls import first_renderable_google_photo

        return first_renderable_google_photo(p)
    except Exception:
        return None



# Marine-signal de-rank for boat_repair. The water bucket is exempt from the
# auto-repair exclusion (a boat ask wants repair shops), so big auto/RV "Car
# Repair" yards ride in on name tokens ("repair"/"service") and, ranked by
# review count, bury the genuine marine shop. We stable-partition so providers
# with a marine signal lead, preserving the existing rank within each group.
_MARINE_SIGNAL_RE = re.compile(
    r"\b(marine|boat|watercraft|outboard|pontoon|jet[\s-]?ski)\b",
    re.IGNORECASE,
)


def _has_marine_signal(p: Provider) -> bool:
    hay = " ".join(
        str(v or "")
        for v in (p.provider_name, p.google_primary_category, p.category)
    )
    return bool(_MARINE_SIGNAL_RE.search(hay))


def _marine_first(rows: list[Provider]) -> list[Provider]:
    """Stable: marine-signal providers first, others (auto/RV) after."""
    marine = [p for p in rows if _has_marine_signal(p)]
    rest = [p for p in rows if not _has_marine_signal(p)]
    return marine + rest


@lru_cache(maxsize=1)
def _primary_leaf_name_by_entity() -> dict[str, str]:
    """``entity_id -> primary-leaf Category.name`` — the authoritative per-listing
    category label (2026-06-30 search audit 3B). Preferred over the unreliable
    ``google_primary_category`` ("Rv Park", "Indoor Playground") / legacy
    ``category`` for the card tag. Cached once per process (categories are
    near-static; a reclass shows after the next deploy). Best-effort: ``{}`` on
    any failure so the label falls back to the legacy heuristics."""
    try:
        from app.db.database import SessionLocal

        with SessionLocal() as db:
            rows = (
                db.query(EntityCategory.entity_id, Category.name)
                .join(Category, Category.id == EntityCategory.category_id)
                .filter(EntityCategory.is_primary.is_(True))
                .all()
            )
        return {eid: name for eid, name in rows if eid and name}
    except Exception:  # pragma: no cover - defensive; label just falls back
        return {}


def _provider_to_row(p: Provider) -> dict[str, Any]:
    """Tier2 provider-row shape consumed by build_business_list."""
    from app.contrib.ingest_suppression import clean_placeholder_address

    return {
        "type": "provider",
        "id": p.id,
        "name": p.provider_name,
        "slug": p.slug,
        "phone": p.phone,
        # The CVB visitor-center placeholder is never a business location —
        # render nothing rather than a shared fake address (2026-07-01 Phase 3;
        # ingest + the data op null it at the source, this is the render guard).
        "address": clean_placeholder_address(p.address),
        "category": p.category,
        "primary_category_label": _primary_leaf_name_by_entity().get(p.entity_id),
        "google_primary_category": p.google_primary_category,
        "google_rating": p.google_rating,
        "google_review_count": p.google_review_count,
        "hours_structured": p.hours_structured,
        "description": p.description,
        "tier": p.tier,
        "sponsored_until": p.sponsored_until,
        "thumb_url": _thumb_url(p),
    }


# ---------------------------------------------------------------------------
# Event window helper + rows
# ---------------------------------------------------------------------------


def _event_window_dates(window: str, today: date) -> tuple[date, date]:
    from app.events.queries import event_window_for_chip

    if window == "today":
        return today, today
    if window == "tomorrow":
        t = today + timedelta(days=1)
        return t, t
    if window == "this_weekend":
        return event_window_for_chip("this-weekend", today=today)
    if window == "this_week":
        return event_window_for_chip("this-week", today=today)
    if window == "next_week":
        monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
        return monday, monday + timedelta(days=6)
    if window == "next_month":
        return event_window_for_chip("next-month", today=today)
    return today, today + timedelta(days=30)


def _event_to_row(event, occ: date) -> dict[str, Any]:
    """Tier2 event-row shape consumed by build_day_agenda / build_week_strip."""
    return {
        "type": "event",
        "name": event.title,
        "date": occ.isoformat(),
        "end_date": event.end_date.isoformat() if event.end_date else None,
        "start_time": event.start_time.strftime("%H:%M") if event.start_time else None,
        "end_time": event.end_time.strftime("%H:%M") if event.end_time else None,
        "location_name": event.location_name,
        "tags": list(event.tags or []),
        "event_url": event.event_url,
    }


def _query_events(
    db: Session, window: str, *, today: date, activity: str | None
) -> list[dict[str, Any]]:
    from app.events.event_type_tags import (
        EVENT_TYPE_LABELS,
        LIVE_MUSIC,
        event_type_label,
        is_civic_meeting,
    )
    from app.events.queries import events_in_window

    start, end = _event_window_dates(window, today)
    pairs = events_in_window(db, window_start=start, window_end=end, limit=_EVENT_LIMIT)
    rows: list[dict[str, Any]] = []
    for event, occ in pairs:
        title = event.title
        venue = getattr(event, "location_name", "") or ""
        desc = getattr(event, "description", "") or ""
        if activity == "live_music":
            # 2026-06-30 audit A2: "live music tonight" must return only ACTUAL
            # live music -- a real performance signal, not a paint-and-sip that
            # merely sits at a brewery. event_type_label requires that signal.
            if event_type_label(title, event.tags, venue, desc) != EVENT_TYPE_LABELS[LIVE_MUSIC]:
                continue
        elif is_civic_meeting(title, desc, venue):
            # Generic "things to do" / "what's happening" browse: government
            # meetings (City Council, P&Z, Board of Adjustment) are not leisure
            # activities -- keep them out of the concierge's events list.
            continue
        rows.append(_event_to_row(event, occ))
    return rows


# ---------------------------------------------------------------------------
# Programs (kids lessons / classes) -- cost + age live here, not on Event.
# ---------------------------------------------------------------------------


def _safe_time_label(t) -> str:
    if t is None:
        return ""
    suffix = "AM" if t.hour < 12 else "PM"
    h12 = t.hour % 12 or 12
    return f"{h12}:{t.minute:02d} {suffix}" if t.minute else f"{h12} {suffix}"


def _offering_by_program(db: Session, programs: list[Program]) -> dict[str, Offering]:
    """Map program id -> its entity's first priced ``Offering``.

    Price "lives on offerings": Program.provider_id -> Provider.entity_id ->
    Offering.entity_id. Picks the lowest-display_order offering that actually
    carries a price; programs with no linked priced offering are absent (the
    caller falls back to ``Program.cost``). Two batched queries, no N+1.
    """
    prov_ids = {p.provider_id for p in programs if p.provider_id}
    if not prov_ids:
        return {}
    ent_by_prov = dict(
        db.query(Provider.id, Provider.entity_id).filter(Provider.id.in_(prov_ids)).all()
    )
    eids = {e for e in ent_by_prov.values() if e}
    if not eids:
        return {}
    priced_by_eid: dict[str, Offering] = {}
    for off in (
        db.query(Offering).filter(Offering.entity_id.in_(eids)).order_by(Offering.display_order).all()
    ):
        if off.entity_id not in priced_by_eid and format_offering_price(off):
            priced_by_eid[off.entity_id] = off
    out: dict[str, Offering] = {}
    for p in programs:
        eid = ent_by_prov.get(p.provider_id) if p.provider_id else None
        if eid and eid in priced_by_eid:
            out[p.id] = priced_by_eid[eid]
    return out


# Venue-name tokens that never identify a venue (town words + connectors).
# "Lake Havasu City Aquatic Center" and the events feed's "Lake Havasu Aquatic
# Center" must both reduce to {aquatic, center}.
_VENUE_STOP_TOKENS: frozenset[str] = frozenset(
    {"the", "a", "an", "of", "and", "at", "in", "on",
     "lake", "havasu", "city", "arizona", "az", "lhc"}
)


def _venue_core_tokens(venue: str) -> list[str]:
    return [
        t
        for t in re.split(r"[^a-z0-9]+", (venue or "").lower())
        if t and t not in _VENUE_STOP_TOKENS
    ]


def _fmt_time(t: time) -> str:
    """12-hour 'H:MM AM' label. Cross-platform — ``%-I`` is glibc-only and
    raises ``ValueError: Invalid format string`` on Windows (and ``%#I`` is the
    MSVC spelling), so compute the hour/meridiem directly instead of strftime."""
    hour12 = t.hour % 12 or 12
    meridiem = "AM" if t.hour < 12 else "PM"
    return f"{hour12}:{t.minute:02d} {meridiem}"


def _query_venue_schedule(
    db: Session, venue: str, *, today: date, limit: int = _PROVIDER_LIMIT
) -> list[dict[str, Any]]:
    """Programs + upcoming events at a matched venue (2026-06-06 gap report:
    "what water exercise classes does the aquatic center offer and when" paid
    Tier 3). Match = every core venue token appears in the row's provider/
    location name (per-token ilike, AND), so feed spelling variants still hit
    while "Mudshark Pizza" can never match "Mudshark Brewery and Public House".
    """
    core = _venue_core_tokens(venue)
    if not core:
        return []
    rows: list[dict[str, Any]] = []

    pq = db.query(Program).filter(Program.is_active.is_(True))
    for tok in core:
        like = f"%{tok}%"
        pq = pq.filter(
            or_(Program.provider_name.ilike(like), Program.location_name.ilike(like))
        )
    programs = pq.limit(limit).all()
    offering_by_prog = _offering_by_program(db, programs)
    for prog in programs:
        days = ", ".join(prog.schedule_days) if prog.schedule_days else ""
        start = _fmt_time(prog.schedule_start_time) if prog.schedule_start_time else ""
        when = " ".join(b for b in (days, start) if b)
        rows.append(
            {
                "type": "program",
                "name": prog.title,
                "subtitle": when or prog.location_name,
                "detail": format_program_price(prog.cost, offering_by_prog.get(prog.id)),
            }
        )

    eq = db.query(Event).filter(Event.status == "live", Event.date >= today)
    for tok in core:
        eq = eq.filter(Event.location_name.ilike(f"%{tok}%"))
    events = eq.order_by(Event.date, Event.start_time).limit(limit).all()
    for ev in events:
        start = _fmt_time(ev.start_time) if ev.start_time else ""
        rows.append(
            {
                "type": "event",
                "name": ev.title,
                "subtitle": " ".join(b for b in (ev.date.isoformat(), start) if b),
                "detail": "",
            }
        )
    return rows[:limit]


def _query_programs(
    db: Session,
    *,
    age_band: str | None,
    activity_category: str | None = None,
    limit: int = _PROVIDER_LIMIT,
) -> list[dict[str, Any]]:
    q = db.query(Program).filter(Program.is_active.is_(True))
    if activity_category:
        q = q.filter(Program.activity_category.ilike(f"%{activity_category}%"))
    rng = dicts.age_band_range(age_band)
    if rng is not None:
        lo, hi = rng
        # Overlap: program's [age_min, age_max] intersects the band. NULL age
        # bounds are treated as open (kept) so thin age data degrades gracefully.
        q = q.filter(
            or_(Program.age_min.is_(None), Program.age_min <= hi),
            or_(Program.age_max.is_(None), Program.age_max >= lo),
        )
    programs = q.limit(limit).all()
    offering_by_prog = _offering_by_program(db, programs)
    rows: list[dict[str, Any]] = []
    for prog in programs:
        days = ", ".join(prog.schedule_days) if prog.schedule_days else ""
        sub_bits = [b for b in (prog.provider_name, days) if b]
        rows.append(
            {
                "type": "program",
                "name": prog.title,
                "subtitle": " · ".join(sub_bits),
                # Price lives on offerings; fall back to the program's freeform cost.
                "detail": format_program_price(prog.cost, offering_by_prog.get(prog.id)),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# classes_find topical guard (2026-06-30 search audit A1)
# ---------------------------------------------------------------------------
# A bare "what classes are offered" browse legitimately lists every active
# program. But "golf lessons" / "wake surf lessons" / "wakeboard lessons" name a
# SPECIFIC activity the catalog doesn't teach -- and the old handler, finding no
# resolver topic, dumped the full Parks & Rec after-school roster (ASP Oro
# Grande, Camp Iwannago...) as if it answered the query. The guard below pulls
# the activity nouns a class query carries; when it names one, a program must
# actually match it, else we return nothing so the honest gap template answers.
_CLASS_BROWSE_FILLER: frozenset[str] = frozenset(
    """a an and any are around at available browse camp camps class classes
    clinic clinics course courses do does enroll find for get go going have has
    here how i im in is it join learn lesson lessons list local looking me my
    near nearby need now of offer offered offering offerings offers on or our
    program programs provide provided provides register registration session
    sessions sign signup some take taught teach teaches teaching the their there
    this to town up us want we what whats when where which who with workshop
    workshops would you your""".split()
) | frozenset({"lake", "havasu", "city", "arizona", "az", "lhc"})


def _class_activity_terms(raw_query: str | None) -> list[str]:
    """Distinctive activity nouns in a class/lesson query ("golf lessons" ->
    ["golf"]). Empty for a generic browse ("what classes are offered") whose
    every token is a class/schedule/filler/locality word -- that still lists all."""
    toks = re.split(r"[^a-z0-9]+", (raw_query or "").lower())
    return [t for t in toks if t and t not in _CLASS_BROWSE_FILLER and not t.isdigit()]


def _program_row_matches_terms(row: dict[str, Any], terms: list[str]) -> bool:
    """True when any activity term appears in the program row's name/subtitle."""
    hay = f"{row.get('name', '')} {row.get('subtitle', '')}".lower()
    return any(t in hay for t in terms)


# ---------------------------------------------------------------------------
# Broad-bucket topical gate (2026-07-01 consolidated search audit A1 / 2.B)
# ---------------------------------------------------------------------------
# The classes_find guard above, generalized to PROVIDER buckets. A broad-bucket
# intent ("shopping", "on the water", "places to stay") legitimately lists its
# whole bucket -- but "gun store" resolved to shopping_find on the bare "store"
# token and answered with golf carts and a fabric shop, "tubing" surfaced an
# RV-parts store, and "golf cart rental" returned boat companies. The gate
# extracts the topical nouns a bucket query carries; when it names one and NO
# returned row matches it, the bucket answer is wrong -- return nothing so the
# honest gap template answers instead of Tier 3 guessing an out-of-area business.

#: Intents whose result set is a broad category bucket, where an unmatched
#: topical noun means the rows do NOT answer the query. find_service /
#: urgent_care are deliberately absent -- their SERVICE_DICT / SYMPTOM_MAP hit
#: IS the topical match ("plumber" is not a substring of "plumbing").
TOPIC_GATED_PROVIDER_INTENTS: frozenset[str] = frozenset(
    {
        "shopping_find",
        "lodging_find",
        "on_the_water",
        "boat_rental",
        "boat_repair",
        "gym_fitness",
        "yoga_pilates",
        "martial_arts",
        "pickleball",
    }
)

# Generic bucket nouns on top of the ranking stopwords: naming the bucket
# ("store", "hotel", "rental", "restaurant") carries no topical signal -- every
# row in the bucket is one. What survives is the activity/product noun that
# must actually appear somewhere on a row ("gun", "tubing", "kayak", "weight").
_PROVIDER_BROWSE_FILLER: frozenset[str] = _RANK_STOP_TERMS | frozenset(
    """store stores shop shops rental rentals rent rented renting hire hotel
    hotels motel motels stay staying place places business businesses company
    companies buy shopping eat eats food dining dine restaurant restaurants
    meal meals dinner lunch brunch supper snack snacks grab bite bites hungry
    repair repairs service services
    should shall anything anywhere somewhere someplace
    exist exists available availability offer offers offering options option
    recommend recommends recommendation recommendations suggest suggestions""".split()
)

# Per-intent bucket trigger nouns: the words that RESOLVED the query to this
# bucket describe the bucket itself, not a narrower topic within it ("gym" must
# not topical-gate the gyms list; "pickleball" must not gate the courts list).
_INTENT_BUCKET_NOUNS: dict[str, frozenset[str]] = {
    "gym_fitness": frozenset(
        "gym gyms fitness crossfit workout workouts weights".split()
    ),
    "yoga_pilates": frozenset("yoga pilates barre studio studios".split()),
    "martial_arts": frozenset(
        "martial arts karate jiu jitsu bjj judo taekwondo dojo".split()
    ),
    "pickleball": frozenset("pickleball tennis racquet court courts".split()),
}


def _provider_activity_terms(raw_query: str | None, intent_key: str = "") -> list[str]:
    """Distinctive topical nouns in a bucket query ("gun store" -> ["gun"]).

    Mirrors :func:`_class_activity_terms`: tokenize, drop filler / bucket nouns /
    short tokens / digits. Empty for a generic bucket browse ("shopping in lake
    havasu", "places to stay") -- those still list the whole bucket."""
    skip = _PROVIDER_BROWSE_FILLER | _INTENT_BUCKET_NOUNS.get(intent_key, frozenset())
    out: list[str] = []
    for tok in re.split(r"[^a-z0-9]+", (raw_query or "").lower()):
        if len(tok) < 3 or tok.isdigit() or tok in skip or tok in out:
            continue
        out.append(tok)
    return out


def _topic_pattern(term: str) -> re.Pattern[str]:
    """Word-boundary matcher with singular/plural tolerance ("gym" matches
    "gyms", "church" matches "churches"). Substring matching would false-pass
    ("side" in "Riverside"), so the boundary is required."""
    stem = term[:-1] if term.endswith("s") and len(term) > 3 else term
    return re.compile(rf"\b{re.escape(stem)}(?:e?s)?\b")


def _topical_gate(
    db: Session, rows: list[Provider], raw_query: str | None, intent_key: str
) -> list[Provider]:
    """Empty a broad-bucket result whose rows never mention the query's topic.

    All-or-nothing: if ANY row matches a topical term the whole list survives
    (the relevance ranking already floats the matches); if none does, the
    bucket does not answer the query and the honest gap template should."""
    terms = _provider_activity_terms(raw_query, intent_key)
    if not terms or not rows:
        return rows
    slugs_by_eid = _leaf_slugs_for_entities(
        db, [p.entity_id for p in rows if p.entity_id]
    )
    patterns = [_topic_pattern(t) for t in terms]
    for p in rows:
        hay = _provider_searchable(p, slugs_by_eid.get(p.entity_id, ()))
        if any(pat.search(hay) for pat in patterns):
            return rows
    return []


# ---------------------------------------------------------------------------
# Gas
# ---------------------------------------------------------------------------


def _query_gas(db: Session) -> list[dict[str, Any]]:
    res = read_source(db, SOURCE_GAS)
    if res is None or not isinstance(res.data, dict):
        return []
    stations = res.data.get("stations")
    if not isinstance(stations, list):
        return []
    priced: list[tuple[float, dict]] = []
    for st in stations:
        if not isinstance(st, dict):
            continue
        prices = st.get("prices") if isinstance(st.get("prices"), dict) else st
        regular = prices.get("regular") if isinstance(prices, dict) else None
        try:
            val = float(regular)
        except (TypeError, ValueError):
            continue
        priced.append((val, st))
    priced.sort(key=lambda x: x[0])
    rows: list[dict[str, Any]] = []
    for val, st in priced[:5]:
        name = str(st.get("name") or st.get("brand") or "Gas station")
        addr = st.get("address") or ""
        rows.append(
            {
                "type": "gas",
                "name": name,
                "subtitle": str(addr),
                "detail": f"${val:.2f}/gal regular",
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_EAT_LEAD = "Here's what's good to eat:"
_SERVICE_LEAD = "Here's who can help:"


def run_query(
    resolved: ResolvedIntent,
    db: Session,
    *,
    today: date | None = None,
    now: datetime | None = None,
    raw_query: str | None = None,
) -> QueryResult:
    key = resolved.intent_key
    slots = resolved.slots
    if today is None:
        today = now_lake_havasu().date()
    # Within-category ranking (P1-1): distinctive query terms used to re-order
    # listing buckets. Empty (no raw_query, or all-generic query) is a no-op and
    # keeps the legacy rating-only sort.
    rank_terms = _derive_rank_terms(raw_query)

    if key == "cheapest_gas":
        return QueryResult(key, "gas", _query_gas(db), None, "Cheapest gas in town right now:")

    if key.startswith("events_"):
        window = str(slots.get("window") or "upcoming")
        activity = slots.get("activity")
        rows = _query_events(
            db, window, today=today, activity=activity if isinstance(activity, str) else None
        )
        return QueryResult(
            key, "events", rows, "events", "Here's what's coming up:", window=window
        )

    if key in ("find_service", "urgent_care"):
        if key == "urgent_care":
            route = dicts.SYMPTOM_MAP.get(str(slots.get("symptom") or ""))
            subcats = ("health-medical",)
            name_tokens = route.name_tokens if route else ()
            legacy: tuple[str, ...] = ("health_medical",)
            label = "clinics"
        else:
            sroute = dicts.SERVICE_DICT.get(str(slots.get("service") or ""))
            if sroute is None:
                return QueryResult(key, "providers", [], "services", _SERVICE_LEAD)
            subcats = (sroute.subcat,)
            name_tokens = sroute.name_tokens
            legacy = sroute.legacy_categories
            label = str(slots.get("service") or "businesses")
        rows = _query_providers(
            db,
            subcats=subcats,
            legacy_categories=legacy,
            name_tokens=name_tokens,
            district=_area(slots),
            open_now=bool(slots.get("open_now")),
            rank_terms=rank_terms,
            now=now,
        )
        return QueryResult(
            key,
            "providers",
            [_provider_to_row(p) for p in rows],
            "services",
            _SERVICE_LEAD,
            label=label,
        )

    if key in ("eat_find", "eat_open_now"):
        cuisine = str(slots.get("cuisine") or "")
        name_tokens = dicts.CUISINE_DICT.get(cuisine, ())
        subcats = dicts.EAT_SUBCATS
        if cuisine in dicts.CUISINE_TO_SUBCAT:
            subcats = (dicts.CUISINE_TO_SUBCAT[cuisine],)
        rows = _query_providers(
            db,
            subcats=subcats,
            legacy_categories=dicts.EAT_LEGACY_CATEGORIES,
            name_tokens=name_tokens,
            district=_area(slots),
            open_now=bool(slots.get("open_now")) or key == "eat_open_now",
            rank_terms=rank_terms,
            now=now,
        )
        if key == "eat_find" and not cuisine:
            # No cuisine slot narrowed the bucket, so a topical noun the rows
            # never mention means the generic restaurant list is not the answer.
            rows = _topical_gate(db, rows, raw_query, key)
        return QueryResult(
            key,
            "providers",
            [_provider_to_row(p) for p in rows],
            "food_drink",
            _EAT_LEAD,
            label=f"{cuisine} spot" if cuisine else "restaurant",
        )

    if key in ("gym_fitness", "yoga_pilates", "martial_arts", "pickleball"):
        subcat = {
            "gym_fitness": "gyms",
            "yoga_pilates": "studios",
            "martial_arts": "martial-arts",
            "pickleball": "racquet-sports",
        }[key]
        label = {
            "gym_fitness": "gym",
            "yoga_pilates": "studio",
            "martial_arts": "martial arts studio",
            "pickleball": "court",
        }[key]
        rows = _query_providers(
            db,
            subcats=(subcat,),
            legacy_categories=("fitness_sports", "fitness"),
            rank_terms=rank_terms,
            now=now,
        )
        rows = _topical_gate(db, rows, raw_query, key)
        return QueryResult(
            key,
            "providers",
            [_provider_to_row(p) for p in rows],
            "classes_sports_recreation",
            "Here's where to break a sweat:",
            label=label,
        )

    if key == "venue_schedule":
        venue = str(slots.get("venue") or "")
        if today is None:
            today = now_lake_havasu().date()
        rows = _query_venue_schedule(db, venue, today=today)
        return QueryResult(
            key,
            "programs",
            rows,
            "venue_schedule",
            f"On the calendar at {venue}:",
            label=venue,
        )

    if key == "kids_lessons":
        rows = _query_programs(db, age_band=str(slots.get("age_band") or "kids"))
        return QueryResult(
            key, "programs", rows, "classes_sports_recreation", "Classes for the kids:"
        )

    if key == "classes_find":
        topic = str(slots.get("topic") or "") or None
        rows = _query_programs(db, age_band=None, activity_category=topic)
        if topic is None:
            # 2026-06-30 audit A1: a query naming a specific activity the catalog
            # doesn't teach ("golf lessons", "wake surf lessons") must return
            # nothing -- never the full Parks & Rec after-school roster. Only a
            # true topic-less browse ("what classes are offered") lists them all.
            terms = _class_activity_terms(raw_query)
            if terms:
                rows = [r for r in rows if _program_row_matches_terms(r, terms)]
        lead = f"{topic.title()} classes around town:" if topic else "Classes and programs around town:"
        return QueryResult(key, "programs", rows, "classes_sports_recreation", lead)

    if key == "lodging_find":
        rows = _query_providers(
            db,
            subcats=dicts.STAY_SUBCATS,
            legacy_categories=dicts.STAY_LEGACY_CATEGORIES,
            district=_area(slots),
            rank_terms=rank_terms,
            now=now,
        )
        rows = _topical_gate(db, rows, raw_query, key)
        return QueryResult(
            key,
            "providers",
            [_provider_to_row(p) for p in rows],
            "lodging_vacation_rentals",
            "Places to stay:",
            label="hotel",
        )

    if key == "shopping_find":
        rows = _query_providers(
            db,
            subcats=dicts.SHOPPING_SUBCATS,
            legacy_categories=dicts.SHOPPING_LEGACY_CATEGORIES,
            district=_area(slots),
            rank_terms=rank_terms,
            now=now,
        )
        rows = _topical_gate(db, rows, raw_query, key)
        return QueryResult(
            key,
            "providers",
            [_provider_to_row(p) for p in rows],
            "shopping_essentials",
            "Where to shop:",
            label="shop",
        )

    if key in ("boat_rental", "boat_repair", "on_the_water"):
        # Rent / repair narrow the on-the-water bucket by name token; the general
        # on_the_water ask returns the whole bucket. Tokens are a soft narrowing
        # within the bucket -- an empty result falls through to the honest gap.
        name_tokens: tuple[str, ...] = ()
        exclude_name_tokens: tuple[str, ...] = ()
        if key == "boat_rental":
            name_tokens = ("rent", "rental", "boat", "kayak", "paddle", "watercraft")
            # The "boat" token also matches storage/repair yards ("Boat Storage of
            # Lake Havasu", "... Boat Repair") -- exclude them from the rental list.
            exclude_name_tokens = ("storage", "repair", "mechanic")
            lead = "Where to get out on the water:"
            label = "rental"
        elif key == "boat_repair":
            name_tokens = ("repair", "service", "marine", "boat")
            lead = "Boat service and repair:"
            label = "shop"
        else:
            lead = "Out on the water:"
            label = "spot"
        # The general "on the water" + "rent a boat" asks must not surface storage
        # yards / auto-RV repair / RV parks that ride in on the broad legacy
        # lake_recreation tag. boat_repair is exempt -- that ask wants repair shops.
        water_exclude_google = () if key == "boat_repair" else dicts.WATER_EXCLUDE_GOOGLE
        rows = _query_providers(
            db,
            subcats=dicts.WATER_SUBCATS,
            legacy_categories=dicts.WATER_LEGACY_CATEGORIES,
            name_tokens=name_tokens,
            exclude_name_tokens=exclude_name_tokens,
            exclude_google_categories=water_exclude_google,
            district=_area(slots),
            rank_terms=rank_terms,
            now=now,
        )
        if key == "boat_repair":
            # Float genuine marine shops above auto/RV "Car Repair" yards.
            rows = _marine_first(rows)
        rows = _topical_gate(db, rows, raw_query, key)
        return QueryResult(
            key,
            "providers",
            [_provider_to_row(p) for p in rows],
            "on_the_water",
            lead,
            label=label,
        )

    if key == "parks_trails":
        rows = _query_providers(
            db,
            subcats=dicts.RECREATION_SUBCATS,
            legacy_categories=dicts.RECREATION_LEGACY_CATEGORIES,
            exclude_google_categories=dicts.RECREATION_EXCLUDE_GOOGLE,
            district=_area(slots),
            rank_terms=rank_terms,
            now=now,
        )
        return QueryResult(
            key,
            "providers",
            [_provider_to_row(p) for p in rows],
            "recreation_outdoors",
            "Parks, trails, and beaches:",
            label="spot",
        )

    if key == "civic_resources":
        rows = _query_providers(
            db,
            subcats=dicts.CIVIC_SUBCATS,
            legacy_categories=dicts.CIVIC_LEGACY_CATEGORIES,
            district=_area(slots),
            rank_terms=rank_terms,
            now=now,
        )
        return QueryResult(
            key,
            "providers",
            [_provider_to_row(p) for p in rows],
            "civic_community",
            "Community resources:",
            label="resource",
        )

    # Unknown intent key -> empty (caller falls through / renders nothing).
    return QueryResult(key, "providers", [], None, "")


def _area(slots: dict[str, object]) -> str | None:
    a = slots.get("area")
    return a if isinstance(a, str) and a else None
