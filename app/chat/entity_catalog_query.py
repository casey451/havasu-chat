"""ENTITY-table catalog queries for chat tier 2 (Phase 7)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.routes.category_pages import REF_LAT, REF_LNG, _distance_km_for_entity
from app.chat import tier2_synonyms as _tier2_synonyms
from app.chat.chat_request_context import ChatRequestContext
from app.chat.tier2_schema import Tier2Filters
from app.contrib.hours_helper import is_open_at
from app.core.ranking import CardRankInput, compute_card_rank
from app.core.timezone import now_lake_havasu
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL, ENTITY_TYPE_EVENT
from app.db.models import Category, Entity, EntityCategory, Event, Location, Provider
from app.providers import queries as provider_queries

_category_needle_set = _tier2_synonyms._category_needle_set


def _text_needle(s: str | None) -> str | None:
    if not s or not str(s).strip():
        return None
    return f"%{str(s).strip()}%"


def _truncate(s: str | None, max_len: int) -> str:
    if not s:
        return ""
    t = s.strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


_DAY_ABBR = {
    "monday": "Mon",
    "tuesday": "Tue",
    "wednesday": "Wed",
    "thursday": "Thu",
    "friday": "Fri",
    "saturday": "Sat",
    "sunday": "Sun",
}

_MAX_PROGRAM_LINES = 12


def _schedule_text(sched) -> str | None:
    """Compact human/LLM-readable recurrence, e.g. ``Mon/Wed/Fri 08:00-09:00``."""
    days = "/".join(
        _DAY_ABBR.get(str(d).strip().lower(), str(d).strip()[:3].title())
        for d in (sched.days_of_week or [])
        if str(d).strip()
    )
    times = None
    if sched.start_time is not None:
        times = sched.start_time.strftime("%H:%M")
        if sched.end_time is not None:
            times += "-" + sched.end_time.strftime("%H:%M")
    text = " ".join(part for part in (days, times) if part)
    return text or None


def _program_lines(ent: Entity) -> list[str]:
    """Pair the entity's Offerings with its recurring Schedules into compact lines.

    Pairing strategy (schedules and offerings are separate rows with no FK):
    1. ``Schedule.notes`` == offering name (the schedule-hunt publish path now
       writes the class title into ``notes``).
    2. Positional zip by ascending id when the entity has the same number of
       recurring schedules as offerings (the publish path creates exactly one
       of each per class, so creation order matches; covers rows written
       before ``notes`` was populated).
    Unpaired offerings still render (name + price, no times).
    """
    offerings = sorted(ent.offerings or [], key=lambda o: (o.display_order, o.id))
    if not offerings:
        return []
    scheds = sorted(
        (s for s in (ent.schedules or []) if (s.schedule_type or "") == "recurring"),
        key=lambda s: s.id,
    )
    by_note: dict[str, Any] = {}
    for s in scheds:
        if s.notes and s.notes.strip():
            by_note.setdefault(s.notes.strip().lower(), s)
    zip_ok = not by_note and len(scheds) == len(offerings)
    lines: list[str] = []
    for idx, off in enumerate(offerings):
        sched = by_note.get((off.name or "").strip().lower())
        if sched is None and zip_ok:
            sched = scheds[idx]
        parts = [_truncate(off.name, 80)]
        if sched is not None:
            stext = _schedule_text(sched)
            if stext:
                parts.append(stext)
        if off.price_text:
            parts.append(_truncate(off.price_text, 48))
        lines.append(" | ".join(parts))
    if len(lines) > _MAX_PROGRAM_LINES:
        extra = len(lines) - _MAX_PROGRAM_LINES
        lines = lines[:_MAX_PROGRAM_LINES] + [f"(+{extra} more)"]
    return lines


def _profile_url(ent: Entity, provider: Provider | None, event: Event | None) -> str:
    et = ent.entity_type or ""
    if et == ENTITY_TYPE_COMMERCIAL and provider and provider.slug:
        return f"/provider/{provider.slug}"
    if et == ENTITY_TYPE_EVENT and event is not None:
        return f"/events/{event.id}"
    if ent.slug:
        return f"/provider/{ent.slug}"
    return "/home"


def _entity_row_dict(
    ent: Entity,
    *,
    provider: Provider | None,
    event: Event | None,
    rank_score: float,
) -> dict[str, Any]:
    loc = ent.location
    address = None
    phone = None
    hours = None
    category_label = None
    if provider is not None:
        address = loc.address if loc and loc.address else provider.address
        phone = provider.phone
        hours = _truncate(provider.hours, 120)
        # CH-1 (WP-9): read the canonical primary category (one of the 12),
        # falling back to the legacy ``category`` string while it is still NULL.
        category_label = provider.primary_category or provider.category
    elif loc is not None:
        address = loc.address
    if ent.categories:
        for ec in sorted(ent.categories, key=lambda x: (not x.is_primary, x.id)):
            cobj = ec.category
            if cobj is not None and cobj.name:
                category_label = cobj.name
                break
    row_type = "provider" if provider is not None else "entity"
    return {
        "type": row_type,
        "entity_id": ent.id,
        "name": ent.name,
        "slug": ent.slug,
        "entity_type": ent.entity_type,
        "profile_url": _profile_url(ent, provider, event),
        "category": category_label,
        "address": address,
        "phone": phone,
        "hours": hours,
        "description": _truncate(ent.description, 120),
        "heat_exposure": ent.heat_exposure,
        "rank_score": rank_score,
        "programs": _program_lines(ent),
    }


def _base_entity_stmt(*, category_slugs: tuple[str, ...] | None, boat_mode: bool):
    stmt = (
        select(Entity)
        .join(EntityCategory, EntityCategory.entity_id == Entity.id)
        .join(Category, Category.id == EntityCategory.category_id)
        .outerjoin(
            Provider,
            (Provider.entity_id == Entity.id) & (Entity.entity_type == ENTITY_TYPE_COMMERCIAL),
        )
        .options(
            joinedload(Entity.location),
            selectinload(Entity.categories).joinedload(EntityCategory.category),
            selectinload(Entity.offerings),
            selectinload(Entity.schedules),
        )
        .where(
            Entity.is_active.is_(True),
            or_(
                Entity.entity_type != ENTITY_TYPE_COMMERCIAL,
                and_(
                    Provider.id.isnot(None),
                    Provider.is_active.is_(True),
                    Provider.draft.is_(False),
                ),
                # Carve-out: a commercial venue with NO Provider record at all
                # but with published content (Offerings attached by the
                # schedule-hunt approve flow) is chat-visible. The schedule-hunt
                # import creates bare Entities; without this their approved
                # class schedules can never surface. Entities whose Provider is
                # draft/inactive stay hidden — the provider review gate still
                # applies whenever a Provider row exists.
                and_(Provider.id.is_(None), Entity.offerings.any()),
            ),
        )
    )
    if category_slugs:
        stmt = stmt.where(Category.slug.in_(category_slugs))
    if boat_mode:
        stmt = stmt.where(Entity.boat_access.isnot(None))
    return stmt


def _category_match_entity(ent: Entity, cat: str, provider: Provider | None) -> bool:
    needles = _category_needle_set(cat)
    if not needles:
        return False
    haystacks: list[str] = [(ent.name or "").lower(), (ent.description or "").lower()]
    if provider is not None:
        haystacks.append((provider.category or "").lower())
        # CH-1 (WP-9): include the canonical primary slug so a category needle
        # keyed to the 12 (e.g. "health-wellness-care") still matches.
        haystacks.append((provider.primary_category or "").lower())
        gpc = (provider.google_primary_category or "").lower().replace("_", " ")
        if gpc:
            haystacks.append(gpc)
    for ec in ent.categories or []:
        cobj = ec.category
        if cobj is not None and cobj.name:
            haystacks.append(cobj.name.lower())
        if cobj is not None and getattr(cobj, "slug", None):
            haystacks.append(str(cobj.slug).lower())
    for off in ent.offerings or []:
        if off.name:
            haystacks.append(off.name.lower())
    for needle in needles:
        if not needle:
            continue
        for hay in haystacks:
            if hay and needle in hay:
                return True
    return False


def _fetch_ranked_entities(
    db: Session,
    filters: Tier2Filters,
    ctx: ChatRequestContext,
    *,
    category_slugs: tuple[str, ...] | None,
    limit: int = 80,
) -> list[dict[str, Any]]:
    stmt = _base_entity_stmt(category_slugs=category_slugs, boat_mode=ctx.boat_mode)
    if needle := _text_needle(filters.entity_name):
        stmt = stmt.where(or_(Entity.name.ilike(needle), Entity.description.ilike(needle)))
    if needle := _text_needle(filters.location):
        stmt = stmt.outerjoin(Location, Location.entity_id == Entity.id).where(
            or_(Location.address.ilike(needle), Location.district.ilike(needle))
        )

    rows = list(db.scalars(stmt.limit(limit)).unique().all())
    if ctx.boat_mode:
        rows = [e for e in rows if e.boat_access is not None]
    # One Provider IN(...) fetch reused by both the category filter and the
    # card assembly below — this used to run twice whenever a category filter
    # was present (audit 2026-07-01). The pre-filter superset map is harmless
    # for the later per-entity lookups.
    prov_map = {
        p.entity_id: p
        for p in db.scalars(
            select(Provider).where(Provider.entity_id.in_([e.id for e in rows]))
        ).all()
    }
    if filters.category and filters.category.strip() and not category_slugs:
        cat = filters.category.strip()
        rows = [e for e in rows if _category_match_entity(e, cat, prov_map.get(e.id))]

    now = now_lake_havasu()
    temp = ctx.effective_temperature_f()
    event_map: dict[str, Event] = {}
    if rows:
        event_map = {
            ev.entity_id: ev
            for ev in db.scalars(
                select(Event).where(
                    Event.entity_id.in_([e.id for e in rows]),
                    Event.status == "live",
                )
            ).all()
            if ev.entity_id is not None
        }

    ranked: list[tuple[Entity, float]] = []
    for ent in rows:
        prov = prov_map.get(ent.id)
        is_open = None
        if prov is not None:
            hs = provider_queries.effective_hours_structured(prov)
            if hs and filters.open_now:
                if not is_open_at(hs, now):
                    continue
            is_open_v, _ = provider_queries.is_open_now(prov, now=now)
            is_open = is_open_v
        elif filters.open_now:
            is_open_v, _ = provider_queries.is_open_status_for_entity(ent, now=now)
            if is_open_v is not True:
                continue
            is_open = is_open_v

        inp = CardRankInput(
            distance_km=_distance_km_for_entity(ent, REF_LAT, REF_LNG),
            name=ent.name or "",
            heat_exposure=ent.heat_exposure,
            verified=bool(prov and prov.verified),
            is_open_now=is_open,
            boat_access_populated=ent.boat_access is not None,
            mobile_service=bool(ent.is_mobile_service),
        )
        score = compute_card_rank(inp, now=now, temperature_f=temp)
        ranked.append((ent, score))

    # C6: sort by the score we already computed from the *full* CardRankInput
    # (verified / open-now / mobile / boat / liveness boosts included). The old
    # sort rebuilt a stripped CardRankInput missing those fields, so the boosts
    # never affected order and the emitted rank_score contradicted the ordering.
    # rank_sort_key(inp) == (-compute_card_rank(inp), name), so this is the same
    # ordering rule applied to the real input. Descending score, then name.
    ranked.sort(key=lambda pair: (-pair[1], (pair[0].name or "").lower()))

    out: list[dict[str, Any]] = []
    for ent, score in ranked:
        prov = prov_map.get(ent.id)
        ev = event_map.get(ent.id)
        out.append(_entity_row_dict(ent, provider=prov, event=ev, rank_score=score))
    return out


def query_entities(
    db: Session,
    filters: Tier2Filters,
    ctx: ChatRequestContext,
    *,
    max_rows: int = 8,
) -> list[dict[str, Any]]:
    """Return ENTITY-shaped rows for tier 2 formatter / components."""
    slugs = ctx.multi_domain_category_slugs or None
    if slugs:
        rows = _fetch_ranked_entities(db, filters, ctx, category_slugs=slugs)
    elif filters.category and filters.category.strip():
        # Single-domain: lock to best-matching slug when we can infer it.
        from app.chat.entity_intent import _NOUN_TO_CATEGORY_SLUGS

        cat_low = filters.category.strip().lower()
        slug_lock: tuple[str, ...] | None = None
        for noun, slug_tuple in _NOUN_TO_CATEGORY_SLUGS.items():
            if noun in cat_low or cat_low in noun:
                slug_lock = slug_tuple[:1]
                break
        rows = _fetch_ranked_entities(db, filters, ctx, category_slugs=slug_lock)
    else:
        rows = _fetch_ranked_entities(db, filters, ctx, category_slugs=None)

    if not rows:
        logging.info("entity_catalog_query: no ENTITY rows for filters=%s", filters)
    return rows[:max_rows]


def prefers_entity_catalog(filters: Tier2Filters, ctx: ChatRequestContext) -> bool:
    """True when tier 2 should try the ENTITY catalog before legacy event merge.

    ``open_now`` / ``entity_name`` alone stay on the legacy path so program, event,
    and provider-only fixtures keep working; category, location, and multi-domain
    intents prefer ENTITY rows (with legacy fallback when the ENTITY query is empty).
    """
    if ctx.multi_domain_category_slugs:
        return True
    if filters.category and filters.category.strip():
        return True
    if filters.location and filters.location.strip():
        return True
    return False


__all__ = ["prefers_entity_catalog", "query_entities"]
