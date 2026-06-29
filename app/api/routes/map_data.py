"""Phase 6.4 — map marker JSON for category and themed-group scopes."""

from __future__ import annotations

import time as _time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.routes import category_pages as cat_pages
from app.categories.queries import primary_listing_filter
from app.core.conditions_temperature import read_current_temperature_f
from app.core.ranking import compute_card_rank
from app.core.rate_limit import limiter, public_api_rate_limit
from app.core.timezone import LAKE_HAVASU_TZ, now_lake_havasu
from app.db.database import get_db
from app.db.models import Entity, EntityCategory, Provider
from app.groups.themed_groups import resolve_map_categories
from app.providers import queries as provider_queries

router = APIRouter(tags=["map"])

MAP_MARKER_CAP = 500

# ---------------------------------------------------------------------------
# Per-scope payload cache (audit P-perf: /api/map_data was ~20s on big scopes)
# ---------------------------------------------------------------------------
#
# Marker assembly builds one card view model per entity (several queries each),
# so large scopes pay seconds of DB round-trips. The payload only shifts when
# the catalog or conditions shift, so a short module-level TTL keeps repeat
# pans/loads instant. Mirrors ``app.categories.router._index_cache``;
# ``reset_map_cache()`` is the canonical test seam. 600s (not 3600) because
# marker status lines ("Open now") are time-sensitive.
_MAP_TTL_SECONDS = 600
_map_cache: dict[tuple[str, bool], tuple[float, dict[str, Any]]] = {}


def reset_map_cache() -> None:
    _map_cache.clear()


def _coords_for(ent: Entity, prov: Provider | None) -> tuple[float, float] | None:
    """Resolve a marker's lat/lng.

    Prefers the entity's ``Location`` row (the unified-model source), then
    falls back to ``Provider.lat/lng``. The fallback is what lets providers
    whose entity has no ``locations`` row still render a pin — the bulk of the
    catalog is geocoded on ``Provider`` directly.
    """
    loc = ent.location
    if loc is not None and loc.lat is not None and loc.lng is not None:
        return float(loc.lat), float(loc.lng)
    if prov is not None and prov.lat is not None and prov.lng is not None:
        return float(prov.lat), float(prov.lng)
    return None


def _primary_category_slug(ent: Entity, prov: Provider | None = None) -> str:
    """Canonical primary-category slug for a marker (WP-9 grouped view of the 12).

    Prefers the provider's canonical ``primary_category`` (one of the 12) so the
    map groups markers by the same taxonomy as Home/Explore, falling back to the
    entity's first ``entity_categories`` slug while ``primary_category`` is NULL.
    """
    if prov is not None and getattr(prov, "primary_category", None):
        return str(prov.primary_category)
    for ec in ent.categories or []:
        if ec.category is not None and ec.category.slug:
            return str(ec.category.slug)
    return ""





def _select_provider_entities(
    db: Session,
    *,
    category_slugs: list[str],
    boat_only: bool,
) -> list[Entity]:
    """Select active providers' entities for a map scope (WP-9 / WP-12).

    Scope slugs are the canonical 13 (``TIER_1_CATEGORY_SLUGS``). A provider is
    selected by :func:`primary_listing_filter` — the ONE canonical category clause
    every count surface shares (audit S4): canonical ``primary_category`` in the
    scope, OR (while that column is still NULL) a legacy ``Provider.category`` that
    folds into the scope. Using the shared clause — rather than a map-local legacy
    expansion — is what makes a category's pin count agree with its Home tile and
    Explore header count.
    """
    stmt = (
        select(Entity)
        .join(Provider, Provider.entity_id == Entity.id)
        .options(
            joinedload(Entity.location),
            joinedload(Entity.categories).joinedload(EntityCategory.category),
        )
        .where(
            Entity.is_active.is_(True),
            primary_listing_filter(set(category_slugs)),
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
        )
    )
    if boat_only:
        stmt = stmt.where(Entity.boat_access.isnot(None))
    return list(db.scalars(stmt).unique().all())


@router.get("/api/map_data/{scope_slug}")
@limiter.limit(public_api_rate_limit)
def map_data(
    request: Request,
    scope_slug: str,
    db: Session = Depends(get_db),
    boat: str | None = Query(None),
) -> dict[str, Any]:
    categories = resolve_map_categories(scope_slug)
    if categories is None:
        raise HTTPException(status_code=404, detail="unknown_scope")

    now = now_lake_havasu()
    if now.tzinfo is None:
        now = now.replace(tzinfo=LAKE_HAVASU_TZ)

    boat_only = boat is not None and str(boat).strip() in {"1", "true", "yes"}

    cache_key = (scope_slug.strip().lower(), boat_only)
    cached = _map_cache.get(cache_key)
    if cached is not None and (_time.time() - cached[0]) < _MAP_TTL_SECONDS:
        return cached[1]

    sort_slug = categories[0]

    # Two selection paths, unioned by entity id (additive — never drops a pin
    # the entity-category path already produced):
    #   1. entity-category join — serves non-commercial entities (events,
    #      outdoors, civic) and properly-linked providers.
    #   2. legacy Provider.category — the gap fix, surfacing the bulk of
    #      providers that carry no entity_categories row.
    by_id: dict[str, Entity] = {}
    for ent in cat_pages.select_entities_for_categories(
        db,
        category_slugs=categories,
        district_slug=None,
        boat_only=boat_only,
    ):
        by_id[ent.id] = ent
    for ent in _select_provider_entities(
        db,
        category_slugs=categories,
        boat_only=boat_only,
    ):
        by_id.setdefault(ent.id, ent)
    entities = list(by_id.values())

    eids = [e.id for e in entities]
    prov_by_eid = (
        {
            p.entity_id: p
            for p in db.scalars(select(Provider).where(Provider.entity_id.in_(eids))).all()
        }
        if eids
        else {}
    )

    entities = [e for e in entities if _coords_for(e, prov_by_eid.get(e.id)) is not None]

    rank_inp = cat_pages.rank_inputs_for_category(
        entities,
        category_slug=sort_slug,
        ref_lat=cat_pages.REF_LAT,
        ref_lng=cat_pages.REF_LNG,
        prov_by_eid=prov_by_eid,
        now=now,
    )

    temp_f = read_current_temperature_f(db)

    def sort_key(e: Entity) -> tuple:
        inp = rank_inp[e.id]
        score = compute_card_rank(inp, now=now, temperature_f=temp_f)
        return (-score, (e.name or "").lower())

    entities = sorted(entities, key=sort_key)
    truncated = len(entities) > MAP_MARKER_CAP
    if truncated:
        entities = entities[:MAP_MARKER_CAP]

    markers: list[dict[str, Any]] = []
    for ent in entities:
        coords = _coords_for(ent, prov_by_eid.get(ent.id))
        if coords is None:
            continue
        lat, lng = coords
        # ONE view-model build per marker -- profile URL, status line, and hero
        # photo all come off the same vm (this loop used to build it 3x, the
        # dominant cost of the endpoint).
        vm = provider_queries.build_card_view_model(db, ent.id, now=now)
        markers.append(
            {
                "id": ent.id,
                "name": ent.name,
                "lat": lat,
                "lng": lng,
                "category_slug": _primary_category_slug(ent, prov_by_eid.get(ent.id)),
                "profile_url": (vm.profile_url or "/home") if vm else "/home",
                "status_line": (vm.status_line_text or "") if vm else "",
                "hero_photo_url": vm.hero_photo_url if vm else None,
            }
        )

    payload = {
        "entities": markers,
        "truncated_at_n": truncated,
        "scope_slug": scope_slug.strip().lower(),
    }
    _map_cache[cache_key] = (_time.time(), payload)
    return payload
