"""Tier 3 context block from local catalog (Phase 3.2 - handoff sec 3.3 / 5).

Builds a plain-text context string capped at ~2000 tokens using a word budget
(``MAX_CONTEXT_WORDS``). Excludes draft providers, inactive programs, and past
events. Entity-matched provider (if any) is listed first with full detail.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.chat.chat_request_context import ChatRequestContext
from app.chat.confidence_tier import (
    classify_confidence,
    hedge_phrase,
)
from app.chat.intent_classifier import IntentResult
from app.chat.tier2_formatter import is_confidence_tier_enabled
from app.core.timezone import now_lake_havasu
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import Entity, EntityCategory, Event, Program, Provider
from app.providers.photo_urls import first_renderable_google_photo

MAX_PROVIDERS = 10
MAX_CONTEXT_WORDS = 1500
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


def _fetch_provider_rows(db: Session, entity: str | None) -> list[Provider]:
    """Active, non-draft providers; entity match first; max ``MAX_PROVIDERS``."""
    active = list(
        db.scalars(
            select(Provider).where(Provider.draft.is_(False), Provider.is_active.is_(True))
        ).all()
    )
    if not active:
        return list(
            db.scalars(
                select(Provider)
                .where(Provider.draft.is_(False), Provider.verified.is_(True))
                .order_by(Provider.provider_name.asc())
                .limit(MAX_PROVIDERS)
            ).all()
        )
    if entity:
        matched = [p for p in active if p.provider_name == entity]
        rest = [p for p in active if p.provider_name != entity]
        ordered: list[Provider] = matched + rest
    else:
        ordered = sorted(active, key=lambda p: (not p.verified, p.provider_name or ""))
    return ordered[:MAX_PROVIDERS]


def _fetch_tier3_records(intent_result: IntentResult, db: Session) -> list[Provider]:
    """Shared Provider lookup behind both Tier 3 entry points (Lane CT2.B.1).

    Both ``build_context_for_tier3`` (assembles the LLM context block) and
    ``rows_for_tier3_classification`` (returns dicts shaped for the
    ``_enforce_low_tier_phone`` post-processor) call this helper so the
    two stay in sync. Single underlying query - no duplicate DB round-trip
    on the request path, and no timing skew between what the LLM saw and
    what the post-processor checks against.

    Backlog #42 / spec section 10: this is the "sibling helper" wiring.
    """
    return _fetch_provider_rows(db, intent_result.entity)


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
    _ = query
    _ = chat_ctx
    today = date.today()
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

    providers = _fetch_tier3_records(intent_result, db)
    if not providers:
        return (
            "Context: No verified provider rows are available in the local catalog yet. "
            "Answer conservatively and do not invent businesses or events."
        ), []

    probe_rows = _probe_rows_for_providers(db, providers, today)

    flag_on = is_confidence_tier_enabled()
    now = now_lake_havasu() if flag_on else None

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


def rows_for_tier3_classification(intent_result: IntentResult, db: Session) -> list[dict]:
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
    providers = _fetch_tier3_records(intent_result, db)
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
