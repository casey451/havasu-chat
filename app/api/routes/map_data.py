"""Phase 6.4 — map marker JSON for category and themed-group scopes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import category_pages as cat_pages
from app.core.conditions_temperature import read_current_temperature_f
from app.core.ranking import compute_card_rank
from app.core.timezone import LAKE_HAVASU_TZ, now_lake_havasu
from app.db.database import get_db
from app.db.models import Entity, Provider
from app.groups.themed_groups import resolve_map_categories
from app.providers import queries as provider_queries

router = APIRouter(tags=["map"])

MAP_MARKER_CAP = 500


def _entity_lat_lng(ent: Entity) -> tuple[float, float] | None:
    loc = ent.location
    if loc is None or loc.lat is None or loc.lng is None:
        return None
    return float(loc.lat), float(loc.lng)


def _primary_category_slug(ent: Entity) -> str:
    for ec in ent.categories or []:
        if ec.category is not None and ec.category.slug:
            return str(ec.category.slug)
    return ""


def _status_line_for_entity(
    db: Session, ent: Entity, *, now
) -> str:
    vm = provider_queries.build_card_view_model(db, ent.id, now=now)
    if vm is None:
        return ""
    return vm.status_line_text or ""


def _hero_url_for_entity(db: Session, ent: Entity) -> str | None:
    vm = provider_queries.build_card_view_model(db, ent.id)
    if vm is None:
        return None
    return vm.hero_photo_url


def _profile_url_for_entity(db: Session, ent: Entity) -> str:
    vm = provider_queries.build_card_view_model(db, ent.id)
    if vm is None:
        return "/home"
    return vm.profile_url or "/home"


@router.get("/api/map_data/{scope_slug}")
def map_data(
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
    sort_slug = categories[0]

    entities = cat_pages.select_entities_for_categories(
        db,
        category_slugs=categories,
        district_slug=None,
        boat_only=boat_only,
    )
    entities = [
        e
        for e in entities
        if _entity_lat_lng(e) is not None
    ]

    eids = [e.id for e in entities]
    prov_by_eid = (
        {
            p.entity_id: p
            for p in db.scalars(select(Provider).where(Provider.entity_id.in_(eids))).all()
        }
        if eids
        else {}
    )

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
        coords = _entity_lat_lng(ent)
        if coords is None:
            continue
        lat, lng = coords
        markers.append(
            {
                "id": ent.id,
                "name": ent.name,
                "lat": lat,
                "lng": lng,
                "category_slug": _primary_category_slug(ent),
                "profile_url": _profile_url_for_entity(db, ent),
                "status_line": _status_line_for_entity(db, ent, now=now),
                "hero_photo_url": _hero_url_for_entity(db, ent),
            }
        )

    return {
        "entities": markers,
        "truncated_at_n": truncated,
        "scope_slug": scope_slug.strip().lower(),
    }
