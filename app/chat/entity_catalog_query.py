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
from app.core.ranking import CardRankInput, compute_card_rank, rank_sort_key
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
        category_label = provider.category
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
        stmt = stmt.where(
            or_(Entity.name.ilike(needle), Entity.description.ilike(needle))
        )
    if needle := _text_needle(filters.location):
        stmt = stmt.outerjoin(Location, Location.entity_id == Entity.id).where(
            or_(Location.address.ilike(needle), Location.district.ilike(needle))
        )

    rows = list(db.scalars(stmt.limit(limit)).unique().all())
    if ctx.boat_mode:
        rows = [e for e in rows if e.boat_access is not None]
    if filters.category and filters.category.strip() and not category_slugs:
        cat = filters.category.strip()
        prov_map = {
            p.entity_id: p
            for p in db.scalars(
                select(Provider).where(
                    Provider.entity_id.in_([e.id for e in rows])
                )
            ).all()
        }
        rows = [
            e
            for e in rows
            if _category_match_entity(e, cat, prov_map.get(e.id))
        ]

    now = now_lake_havasu()
    temp = ctx.effective_temperature_f()
    prov_map = {
        p.entity_id: p
        for p in db.scalars(
            select(Provider).where(Provider.entity_id.in_([e.id for e in rows]))
        ).all()
    }
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

    ranked.sort(
        key=lambda pair: rank_sort_key(
            CardRankInput(
                distance_km=_distance_km_for_entity(pair[0], REF_LAT, REF_LNG),
                name=pair[0].name or "",
                heat_exposure=pair[0].heat_exposure,
                boat_access_populated=pair[0].boat_access is not None,
            ),
            now=now,
            temperature_f=temp,
        )
    )

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
        rows = _fetch_ranked_entities(
            db, filters, ctx, category_slugs=slug_lock
        )
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
