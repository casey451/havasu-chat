"""Tier 3 context block from local catalog (Phase 3.2 - handoff sec 3.3 / 5).

Builds a plain-text context string capped at ~2000 tokens using a word budget
(``MAX_CONTEXT_WORDS``). Excludes draft providers, inactive programs, and past
events. Entity-matched provider (if any) is listed first with full detail.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Sequence

from sqlalchemy import String, and_, cast, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.chat.chat_request_context import ChatRequestContext
from app.chat.confidence_tier import (
    classify_confidence,
    hedge_phrase,
)
from app.chat.intent_classifier import IntentResult
from app.chat.normalizer import spell_correct
from app.chat.tier2_formatter import is_confidence_tier_enabled
from app.chat.tier2_synonyms import _CATEGORY_SYNONYM_GROUPS, _category_needle_set
from app.core.timezone import now_lake_havasu
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import Category, Entity, EntityCategory, Event, Program, Provider
from app.providers.photo_urls import first_renderable_google_photo
from app.search import fts as search_fts

MAX_PROVIDERS = 10
MAX_CONTEXT_WORDS = 1500
MAX_STANDALONE_EVENTS = 15
_CANDIDATES_PER_SOURCE = 50
_STANDALONE_EVENTS_MAX_WORDS = 300
_HOURS_MAX_LEN = 200


def _hedge_suffix_for(record, *, now) -> str:
    """Return ``" (<hedge>)"`` for MEDIUM/LOW records, else ``""`` (Lane CT2.B).

    Defensive: any failure inside the classifier returns ``""`` so a
    classification hiccup never breaks context-block assembly.
    """
    try:
        assessment = classify_confidence(record, now=now)
        hedge = hedge_phrase(assessment.tier)
    except Exception:
        logging.exception("context_builder: classify_confidence raised on row, no hedge suffix")
        return ""
    if not hedge:
        return ""
    return f" ({hedge})"


def _truncate_hours(h: str | None) -> str:
    if not h:
        return ""
    s = h.strip()
    if len(s) <= _HOURS_MAX_LEN:
        return s
    return s[: _HOURS_MAX_LEN - 3] + "..."


def _provider_url(p: Provider) -> str | None:
    """Best URL for a recommendation - own website preferred, Google Maps page as fallback."""
    w = (p.website or "").strip()
    if w:
        return w
    pid = (p.google_place_id or "").strip()
    if pid:
        return f"https://www.google.com/maps/place/?q=place_id:{pid}"
    return None


def _word_count(text: str) -> int:
    return len(text.split())


def _trim_to_word_budget(text: str, max_words: int) -> str:
    if _word_count(text) <= max_words:
        return text
    words = text.split()
    return " ".join(words[:max_words])


# C1: when no entity matched, rank the Tier 3 provider snapshot by overlap with
# the user's query instead of feeding a fixed alphabetical-verified slice. The
# query used to be discarded outright (``_ = query``), so open-ended turns always
# saw the same 10 providers regardless of what was asked.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "and", "for", "are", "any", "good", "best", "near", "around",
        "what", "where", "which", "who", "with", "that", "this", "have", "has",
        "can", "you", "your", "find", "show", "list", "give", "some", "there",
        "here", "open", "now", "lake", "havasu", "city", "place", "places",
        "thing", "things", "want", "need", "looking", "recommend", "about",
    }
)


def _query_tokens(query: str | None) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", (query or "").lower())
    return [t for t in toks if len(t) > 2 and t not in _STOPWORDS]


def _provider_relevance(
    p: Provider, tokens: list[str], needles: Sequence[str] = ()
) -> int:
    """Token/needle overlap with the provider's text fields.

    Hunt 2026-06-10 §4b: the old haystack was name+category+address only —
    "plumber" / "bowling" / "electrician" live in ``google_primary_category`` /
    ``google_categories`` and were invisible to the scorer. Google fields are
    normalized (underscores → spaces) and category-needle hits score double so
    a category-confirmed provider outranks an incidental token match.
    """
    if not tokens and not needles:
        return 0
    cat_parts = [p.category or ""]
    gpc = getattr(p, "google_primary_category", None)
    if gpc:
        cat_parts.append(gpc.replace("_", " "))
    gcs = getattr(p, "google_categories", None)
    if isinstance(gcs, list):
        cat_parts.extend(t.replace("_", " ") for t in gcs if isinstance(t, str))
    cat_hay = " ".join(v for v in cat_parts if v).lower()
    text_parts = [p.provider_name or "", getattr(p, "address", None) or "", cat_hay]
    hay = " ".join(v for v in text_parts if v).lower()
    score = sum(1 for t in tokens if t in hay)
    # Needles are category vocabulary — score them against category fields
    # only, so a category-confirmed provider outranks a business that merely
    # has the word in its name ("Plumber Street Tacos").
    score += 2 * sum(1 for n in needles if n and n in cat_hay)
    return score


def _category_vocab_terms(query: str | None) -> list[str]:
    """Known category vocabulary (leaf-map keys + Tier-2 synonym terms) in the query.

    Scans 1- and 2-grams of the tokenized query against the navigational leaf
    dict and the category synonym groups (bigrams first; tokens already covered
    by a captured bigram are skipped), so conversational phrasings — "what is
    the best plumber in lake havasu", "i need a plumber" — surface their
    category term even though leaf-normalize would not collapse them.
    """
    # Lazy import: leaf_query imports app.chat.normalizer at module level;
    # importing it lazily keeps app.chat.context_builder cycle-safe (same
    # pattern as normalizer's lazy vocabulary imports).
    from app.categories.leaf_query import _QUERY_TO_LEAF

    toks = re.findall(r"[a-z0-9]+", (query or "").lower())
    synonym_terms = {t for g in _CATEGORY_SYNONYM_GROUPS for t in g}
    out: list[str] = []
    for n in (2, 1):
        for i in range(len(toks) - n + 1):
            g = " ".join(toks[i : i + n])
            if g in out:
                continue
            if n == 1 and any(g in t.split() for t in out):
                continue
            if g in _QUERY_TO_LEAF or g in synonym_terms:
                out.append(g)
    return out


def _category_needles_for_query(terms: Sequence[str]) -> tuple[str, ...]:
    """Union of Tier-2 needle sets for every category term found in the query."""
    needles: set[str] = set()
    for t in terms:
        needles.update(_category_needle_set(t))
    return tuple(sorted(needles))


def _candidate_providers(
    db: Session, tokens: list[str], terms: Sequence[str], needles: Sequence[str]
) -> list[Provider]:
    """Bounded SQL candidate union — PERF-2: no full-table Provider scan.

    Sources, each capped at ``_CANDIDATES_PER_SOURCE`` and ordered
    verified-first/name (deep dive §4b "push filtering into SQL"):

    (a) service-intent → leaf routing: category terms that resolve through
        ``_QUERY_TO_LEAF`` pull providers via their entity's category rows
        with one batched ``IN`` over leaf slugs;
    (b) category needles vs ``category`` / ``google_primary_category`` /
        ``google_categories`` (ILIKE; underscore variants so "bowling alley"
        matches Google's ``bowling_alley``);
    (c) raw query tokens vs name / category / address — preserves the
        pre-§4b text-match surface;
    (d) FTS over ``entities.search_vector`` (token OR-group) on Postgres,
        Entity name/description ILIKE on SQLite, then one batched
        ``Provider.entity_id IN`` lookup.
    """
    from app.categories.leaf_query import _QUERY_TO_LEAF  # lazy — see above

    base = (Provider.draft.is_(False), Provider.is_active.is_(True))
    order = (Provider.verified.desc(), Provider.provider_name.asc())
    found: dict[Any, Provider] = {}

    def take(stmt) -> None:
        for prov in db.scalars(stmt.limit(_CANDIDATES_PER_SOURCE)).all():
            found.setdefault(prov.id, prov)

    leaf_slugs = sorted(
        {
            slug
            for t in terms
            for slug in (_QUERY_TO_LEAF.get(t), _QUERY_TO_LEAF.get(t + "s"))
            if slug
        }
    )
    if leaf_slugs:
        take(
            select(Provider)
            .join(Entity, Provider.entity_id == Entity.id)
            .join(EntityCategory, EntityCategory.entity_id == Entity.id)
            .join(Category, EntityCategory.category_id == Category.id)
            .where(*base, Category.slug.in_(leaf_slugs))
            .order_by(*order)
        )

    if needles:
        conds: list[Any] = []
        for n in needles:
            variants = {n}
            if " " in n:
                variants.add(n.replace(" ", "_"))
            for v in variants:
                like = f"%{v}%"
                conds.append(Provider.category.ilike(like))
                conds.append(Provider.google_primary_category.ilike(like))
                conds.append(cast(Provider.google_categories, String).ilike(like))
        take(select(Provider).where(*base, or_(*conds)).order_by(*order))

    if tokens:
        conds = []
        for t in tokens:
            like = f"%{t}%"
            conds.append(Provider.provider_name.ilike(like))
            conds.append(Provider.category.ilike(like))
            conds.append(Provider.address.ilike(like))
        take(select(Provider).where(*base, or_(*conds)).order_by(*order))

        if db.get_bind().dialect.name == "postgresql":
            groups = [
                g
                for g in (search_fts._phrase_to_tsquery_group(t) for t in tokens)
                if g
            ]
            ent_ids_stmt = None
            if groups:
                tsq = "(" + " | ".join(groups) + ")"
                ent_ids_stmt = (
                    select(Entity.id)
                    .where(
                        Entity.is_active.is_(True),
                        search_fts.entities_search_vector_match(tsq),
                    )
                    .limit(_CANDIDATES_PER_SOURCE)
                )
        else:
            conds = []
            for t in tokens:
                like = f"%{t}%"
                conds.append(Entity.name.ilike(like))
                conds.append(Entity.description.ilike(like))
            ent_ids_stmt = (
                select(Entity.id)
                .where(Entity.is_active.is_(True), or_(*conds))
                .limit(_CANDIDATES_PER_SOURCE)
            )
        if ent_ids_stmt is not None:
            ent_ids = list(db.scalars(ent_ids_stmt).all())
            if ent_ids:
                take(
                    select(Provider)
                    .where(*base, Provider.entity_id.in_(ent_ids))
                    .order_by(*order)
                )

    return list(found.values())


def _fetch_provider_rows(
    db: Session, entity: str | None, query: str | None = None
) -> list[Provider]:
    """Active, non-draft providers; entity match first, else query-relevant.

    Capped at ``MAX_PROVIDERS``. Hunt 2026-06-10 §4b / PERF-2 rewrite:
    candidates come from bounded SQL (leaf routing, Google-category needles,
    token ILIKE, FTS) instead of a full-table scan, then the small union is
    ranked in Python by :func:`_provider_relevance` — which now sees the
    Google category fields. With no usable tokens the pipeline degrades to
    the prior verified-then-alphabetical ordering (C1), and the verified-only
    fallback for an empty active set is unchanged.
    """
    # Hunt 2026-06-10 §1 item 6 (C-PR-4): spell-correct was only applied at
    # leaf-normalize, so the Tier-3 scorer never saw corrections — "plummbers"
    # leaf-routed fine but Tier-3 retrieval got the raw typo. Correct once here;
    # the shared layer is conservative (cutoff 90, length guards, protected set).
    corrected = spell_correct(query) if query else query
    tokens = _query_tokens(corrected)
    terms = _category_vocab_terms(corrected)
    needles = _category_needles_for_query(terms)

    matched: list[Provider] = []
    if entity:
        matched = list(
            db.scalars(
                select(Provider)
                .where(
                    Provider.draft.is_(False),
                    Provider.is_active.is_(True),
                    Provider.provider_name == entity,
                )
                .order_by(Provider.provider_name.asc())
                .limit(MAX_PROVIDERS)
            ).all()
        )

    candidates = _candidate_providers(db, tokens, terms, needles)
    matched_ids = {p.id for p in matched}
    rest = [p for p in candidates if p.id not in matched_ids]
    rest.sort(
        key=lambda p: (
            -_provider_relevance(p, tokens, needles),
            not p.verified,
            p.provider_name or "",
        )
    )
    ordered: list[Provider] = matched + rest

    if len(ordered) < MAX_PROVIDERS:
        # Pad with the prior degraded ordering (verified-first, then name) so
        # token-less or no-match queries keep their pre-§4b snapshot — bounded
        # LIMIT, not a full-table scan.
        seen = {p.id for p in ordered}
        fill = db.scalars(
            select(Provider)
            .where(Provider.draft.is_(False), Provider.is_active.is_(True))
            .order_by(Provider.verified.desc(), Provider.provider_name.asc())
            .limit(MAX_PROVIDERS + len(seen))
        ).all()
        for prov in fill:
            if prov.id not in seen:
                ordered.append(prov)
                seen.add(prov.id)
            if len(ordered) >= MAX_PROVIDERS:
                break

    if not ordered:
        # No active rows at all: keep the verified-only fallback slice.
        return list(
            db.scalars(
                select(Provider)
                .where(Provider.draft.is_(False), Provider.verified.is_(True))
                .order_by(Provider.provider_name.asc())
                .limit(MAX_PROVIDERS)
            ).all()
        )
    return ordered[:MAX_PROVIDERS]


def _fetch_tier3_records(
    intent_result: IntentResult, db: Session, query: str | None = None
) -> list[Provider]:
    """Shared Provider lookup behind both Tier 3 entry points (Lane CT2.B.1).

    Both ``build_context_for_tier3`` (assembles the LLM context block) and
    ``rows_for_tier3_classification`` (returns dicts shaped for the
    ``_enforce_low_tier_phone`` post-processor) call this helper so the
    two stay in sync. Single underlying query - no duplicate DB round-trip
    on the request path, and no timing skew between what the LLM saw and
    what the post-processor checks against.

    Backlog #42 / spec section 10: this is the "sibling helper" wiring.

    ``query`` is threaded through so the entity-less provider snapshot is ranked
    by query relevance identically on both entry points — the LLM context and
    the post-processor row set stay byte-for-byte the same set. (C1)
    """
    return _fetch_provider_rows(db, intent_result.entity, query=query)


def _programs_for(db: Session, provider_id: str) -> Sequence[Program]:
    return db.scalars(
        select(Program).where(Program.provider_id == provider_id, Program.is_active.is_(True))
    ).all()


def _events_future_for(db: Session, provider_id: str, today: date) -> Sequence[Event]:
    return db.scalars(
        select(Event)
        .where(
            Event.provider_id == provider_id,
            Event.status == "live",
            Event.date >= today,
        )
        .order_by(Event.date.asc(), Event.start_time.asc())
        .limit(8)
    ).all()


def _standalone_events_upcoming(
    db: Session, today: date, *, limit: int = MAX_STANDALONE_EVENTS
) -> Sequence[Event]:
    """Upcoming standalone events — live rows with no provider attachment.

    Hunt 2026-06-10 §1 item 1 (~48 turns/window, the largest miss family):
    "events tomorrow/today/tonight/this weekend" dead-ended because
    ``provider_id IS NULL`` rows never entered Tier-3 context. Date filter:
    starts today or later, OR still running (multi-day: ``end_date >= today``).
    Recurring events are materialized one row per occurrence date, so
    ``date >= today`` covers those. Date-ascending + cap keeps the near-term
    events the demand asks about.
    """
    return db.scalars(
        select(Event)
        .where(
            Event.provider_id.is_(None),
            Event.status == "live",
            or_(
                Event.date >= today,
                and_(Event.end_date.is_not(None), Event.end_date >= today),
            ),
        )
        .order_by(Event.date.asc(), Event.start_time.asc())
        .limit(limit)
    ).all()


def _standalone_events_section(
    db: Session, today: date, *, flag_on: bool, now
) -> tuple[str | None, list[dict[str, Any]]]:
    """Compact context section for standalone events (name · date · venue).

    Returns ``(None, [])`` when there are no upcoming standalone events.
    The section gets its own sub-budget so a long events calendar can never
    crowd provider rows out of ``MAX_CONTEXT_WORDS``; the caller's final
    whole-body trim still applies on top.
    """
    events = _standalone_events_upcoming(db, today)
    if not events:
        return None, []
    lines = ["Local events (standalone listings, not tied to a business above):"]
    for e in events:
        suffix = _hedge_suffix_for(e, now=now) if flag_on else ""
        when = e.date.isoformat()
        if e.end_date is not None and e.end_date != e.date:
            when += f"\u2013{e.end_date.isoformat()}"
        when += f" {e.start_time.strftime('%H:%M')}"
        if e.end_time is not None:
            when += f"\u2013{e.end_time.strftime('%H:%M')}"
        lines.append(f"  Event: {e.title} \u00b7 {when} \u00b7 {e.location_name}{suffix}")
    section = _trim_to_word_budget("\n".join(lines), _STANDALONE_EVENTS_MAX_WORDS)
    return section, [_event_probe_row(e) for e in events]


def _entity_profile_url(ent: Entity, provider: Provider | None) -> str:
    if ent.entity_type == ENTITY_TYPE_COMMERCIAL and provider and provider.slug:
        return f"/provider/{provider.slug}"
    if ent.slug:
        return f"/provider/{ent.slug}"
    return "/home"


def _fetch_entity_rows(db: Session, entity_name: str | None, *, limit: int = 10) -> list[Entity]:
    if not entity_name or not str(entity_name).strip():
        return []
    # Push the case-insensitive exact-name match into SQL so LIMIT can never
    # cut off the matching row. The prior `limit*3` Python-side filter pattern
    # silently failed as soon as the active Entity table grew past ~30 rows:
    # SQLite would return the first 30 by rowid order, the matching row could
    # fall outside that window, and the Python filter would return []. The
    # test `test_entity_matched_provider_listed_first_with_details` failed in
    # CI for exactly this reason once accumulated test-suite Entity rows
    # pushed the active count past 30; it passed locally only when the
    # matching row happened to land in the first 30 by luck. See PR #15 /
    # CIDIAG capture 2026-05-27 (49 baseline active entities; 'Target Biz
    # LLC' outside the LIMIT 30 slice; ctx fell through to Provider branch).
    from sqlalchemy import func

    needle = entity_name.strip().lower()
    q = (
        select(Entity)
        .where(
            Entity.is_active.is_(True),
            func.lower(Entity.name) == needle,
        )
        .options(
            joinedload(Entity.location),
            selectinload(Entity.categories).joinedload(EntityCategory.category),
        )
        .limit(limit)
    )
    return list(db.scalars(q).unique().all())


def _truncate_desc(s: str | None, max_len: int = 120) -> str:
    if not s:
        return ""
    t = s.strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


def _provider_probe_row(p: Provider) -> dict[str, Any]:
    """Dict row for Tier 3 component probes (matches Tier 2 single_card shape)."""
    loc = getattr(getattr(p, "entity", None), "location", None)
    address = loc.address if loc is not None and loc.address else p.address
    return {
        "type": "provider",
        "name": p.provider_name,
        "slug": p.slug,
        "category": p.category,
        "google_primary_category": p.google_primary_category,
        "google_place_id": p.google_place_id,
        "address": address,
        "phone": p.phone,
        "website": p.website,
        "hours": _truncate_hours(p.hours),
        "hours_structured": p.hours_structured,
        "description": _truncate_desc(p.description),
        "google_rating": p.google_rating,
        "google_review_count": p.google_review_count,
        "thumb_url": first_renderable_google_photo(p),
    }


def _event_probe_row(e: Event) -> dict[str, Any]:
    out: dict[str, Any] = {
        "type": "event",
        "name": e.title,
        "date": e.date.isoformat(),
        "start_time": e.start_time.strftime("%H:%M") if e.start_time else None,
        "end_time": e.end_time.strftime("%H:%M") if e.end_time else None,
        "location_name": e.location_name,
        "description": _truncate_desc(e.description),
        "event_url": e.event_url,
        "tags": list(e.tags or [])[:8],
    }
    if e.end_date is not None:
        out["end_date"] = e.end_date.isoformat()
    return out


def _probe_rows_for_providers(
    db: Session, providers: Sequence[Provider], today: date
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in providers:
        rows.append(_provider_probe_row(p))
        for ev in _events_future_for(db, p.id, today):
            rows.append(_event_probe_row(ev))
    return rows


def build_context_and_rows_for_tier3(
    query: str,
    intent_result: IntentResult,
    db: Session,
    *,
    chat_ctx: ChatRequestContext | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Return assembled Tier 3 context plus catalog rows for component probes.

    BUILD.md step 5 Phase 5E: ``context_str`` matches ``build_context_for_tier3``;
    ``rows`` is the provider/event dict list the string was assembled from.
    """
    _ = chat_ctx
    # Lake Havasu date, not the server-local (UTC) date -- date.today() on a
    # UTC host hides the rest of *today's* events from Tier 3 context after 5 PM.
    today = now_lake_havasu().date()
    entities = _fetch_entity_rows(db, intent_result.entity)
    if entities:
        flag_on = is_confidence_tier_enabled()
        now = now_lake_havasu() if flag_on else None
        prov_by_ent = {
            p.entity_id: p
            for p in db.scalars(
                select(Provider).where(
                    Provider.entity_id.in_([e.id for e in entities]),
                    Provider.is_active.is_(True),
                    Provider.draft.is_(False),
                )
            ).all()
        }
        parts: list[str] = [
            "Context — Lake Havasu ENTITY catalog (cite profile_url when recommending):"
        ]
        for ent in entities:
            prov = prov_by_ent.get(ent.id)
            suffix = _hedge_suffix_for(prov or ent, now=now) if flag_on and prov else ""
            url = _entity_profile_url(ent, prov)
            lines = [f"Entity: {ent.name}{suffix}", f"  profile_url: {url}"]
            if ent.description:
                lines.append(f"  description: {_truncate_hours(ent.description)}")
            if ent.heat_exposure:
                lines.append(f"  heat_exposure: {ent.heat_exposure}")
            if ent.boat_access:
                lines.append("  boat_access: yes")
            loc = ent.location
            if loc and loc.address:
                lines.append(f"  address: {loc.address}")
            if prov:
                if prov.phone:
                    lines.append(f"  phone: {prov.phone}")
                if prov.website:
                    lines.append(f"  website: {prov.website}")
                hrs = _truncate_hours(prov.hours)
                if hrs:
                    lines.append(f"  hours: {hrs}")
            parts.append("\n".join(lines))
        body = "\n\n".join(parts)
        probe_rows: list[dict[str, Any]] = []
        for ent in entities:
            prov = prov_by_ent.get(ent.id)
            if prov is not None:
                probe_rows.extend(_probe_rows_for_providers(db, [prov], today))
        return _trim_to_word_budget(body, MAX_CONTEXT_WORDS), probe_rows

    providers = _fetch_tier3_records(intent_result, db, query=query)

    flag_on = is_confidence_tier_enabled()
    now = now_lake_havasu() if flag_on else None

    # Hunt 2026-06-10 §1 item 1: standalone events enter the snapshot path.
    ev_section, ev_rows = _standalone_events_section(db, today, flag_on=flag_on, now=now)

    if not providers:
        if ev_section is None:
            return (
                "Context: No verified provider rows are available in the local catalog yet. "
                "Answer conservatively and do not invent businesses or events."
            ), []
        body = (
            "Context: No verified provider rows are available in the local catalog yet. "
            "Answer conservatively and do not invent businesses. Upcoming local events "
            "below are from the events calendar.\n\n" + ev_section
        )
        return _trim_to_word_budget(body, MAX_CONTEXT_WORDS), ev_rows

    probe_rows = _probe_rows_for_providers(db, providers, today)

    parts: list[str] = []
    parts.append("Context — Lake Havasu catalog snapshot (programs and events may be partial):")
    for p in providers:
        lines: list[str] = []
        suffix = _hedge_suffix_for(p, now=now) if flag_on else ""
        lines.append(f"Provider: {p.provider_name}{suffix}")
        lines.append(f"  category: {p.category}")
        if p.address:
            lines.append(f"  address: {p.address}")
        if p.phone:
            lines.append(f"  phone: {p.phone}")
        if p.website:
            lines.append(f"  website: {p.website}")
        url = _provider_url(p)
        if url:
            lines.append(f"  url: {url}")
        hrs = _truncate_hours(p.hours)
        if hrs:
            lines.append(f"  hours: {hrs}")
        if p.verified:
            lines.append("  verified: yes")
        for prog in _programs_for(db, p.id):
            if prog.age_min is not None or prog.age_max is not None:
                ages = f"{prog.age_min if prog.age_min is not None else '?'}-{prog.age_max if prog.age_max is not None else '?'}"
            else:
                ages = "n/a"
            sched_st = prog.schedule_start_time
            sched_et = prog.schedule_end_time
            sched_st_s = sched_st.strftime("%H:%M") if sched_st is not None else ""
            sched_et_s = sched_et.strftime("%H:%M") if sched_et is not None else ""
            seg = f"  Program: {prog.title} | ages {ages} | schedule {sched_st_s}-{sched_et_s}"
            if prog.cost:
                seg += f" | cost: {prog.cost}"
            if prog.schedule_note:
                sn = prog.schedule_note.strip()
                if len(sn) > 120:
                    sn = sn[:117] + "..."
                seg += f" | note: {sn}"
            lines.append(seg)
        for ev in _events_future_for(db, p.id, today):
            ev_suffix = _hedge_suffix_for(ev, now=now) if flag_on else ""
            lines.append(
                f"  Upcoming event: {ev.title} on {ev.date.isoformat()} "
                f"at {ev.start_time.strftime('%H:%M')} — {ev.location_name}"
                f"{ev_suffix}"
            )
        parts.append("\n".join(lines))

    if ev_section is not None:
        parts.append(ev_section)
        probe_rows.extend(ev_rows)

    body = "\n\n".join(parts)
    body = _trim_to_word_budget(body, MAX_CONTEXT_WORDS)
    return body, probe_rows


def build_context_for_tier3(
    query: str,
    intent_result: IntentResult,
    db: Session,
    *,
    chat_ctx: ChatRequestContext | None = None,
) -> str:
    """Return a plain-text context block for the Tier 3 system prompt (never empty)."""
    context, _rows = build_context_and_rows_for_tier3(query, intent_result, db, chat_ctx=chat_ctx)
    return context


def rows_for_tier3_classification(
    intent_result: IntentResult, db: Session, query: str | None = None
) -> list[dict]:
    """Return Tier 3 Provider rows shaped for the LOW-tier phone post-processor (Lane CT2.B.1).

    Sibling helper to ``build_context_for_tier3``. Both call the shared
    ``_fetch_tier3_records`` query so the row set the LLM saw matches the
    row set the post-processor enforces against - no timing skew, no
    duplicate Provider lookup at the request boundary.

    Each returned dict carries the fields ``_enforce_low_tier_phone``
    inspects: ``phone`` (the candidate the post-processor would inline if
    missing) and ``confidence_hint`` (``"low"`` / ``"medium"`` / ``"high"``
    from the per-row ``classify_confidence`` call). When the feature flag
    is off the helper still returns rows but with ``confidence_hint``
    blanked - the post-processor's tier check then short-circuits without
    touching the response. Defensive: any classifier failure on a single
    row degrades that row to an empty hint (LOW + missing phone =
    no-op anyway).

    The shape is intentionally narrow - the post-processor only reads
    ``phone`` and ``confidence_hint``, so we don't pay to materialize
    Programs / Events here. Backlog #42 (spec section 10): future telemetry
    optimization to cache this list inside the request lives at the
    handler level, not here.
    """
    providers = _fetch_tier3_records(intent_result, db, query=query)
    if not providers:
        return []
    flag_on = is_confidence_tier_enabled()
    now = now_lake_havasu() if flag_on else None
    out: list[dict] = []
    for p in providers:
        hint = ""
        if flag_on:
            try:
                assessment = classify_confidence(p, now=now)
                hint = assessment.tier.value
            except Exception:
                logging.exception(
                    "context_builder: classify_confidence raised on row, skipping confidence_hint"
                )
                hint = ""
        out.append(
            {
                "type": "provider",
                "provider_name": p.provider_name,
                "phone": p.phone or "",
                "confidence_hint": hint,
            }
        )
    return out
