"""Tier 1 category landing pages (Phase 6.2).

GET /category/<slug> renders the shared shell + organic Hava card stream.
Eat & Drink is the first proof category; other Tier 1 slugs reuse the template.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.timezone import LAKE_HAVASU_TZ, now_lake_havasu
from app.db.database import get_db
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import Category, District, Entity, EntityCategory, Provider
from app.home.queries import CATEGORY_LABELS
from app.providers import queries as provider_queries
from app.providers.queries import _parse_hours_time, is_open_now

router = APIRouter(tags=["category"])

_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@dataclass(frozen=True)
class Chip:
    slug: str
    label: str


TIER_1_CATEGORY_SLUGS: frozenset[str] = frozenset(
    {
        "eat-drink",
        "on-the-water",
        "home-property-services",
        "health-wellness-care",
        "auto-rv-fuel",
        "shopping-essentials",
    }
)

# Anonymous default anchor — Lake Havasu City approximate civic center.
_REF_LAT = 34.4839
_REF_LNG = -114.3225

DEFAULT_SORT_BY_SLUG: dict[str, str] = {
    "eat-drink": "closest_now",
    "on-the-water": "closest_now",
    "home-property-services": "editorial_pick",
    "health-wellness-care": "closest_now",
    "auto-rv-fuel": "closest_now",
    "shopping-essentials": "closest_now",
}

_CATEGORY_ONE_LINERS: dict[str, str] = {
    "eat-drink": "Restaurants, cafés, bars, and local flavors.",
    "on-the-water": "Marinas, launches, rentals, and lake life.",
    "home-property-services": "Trusted pros for your home and property.",
    "health-wellness-care": "Care, wellness, and fitness around town.",
    "auto-rv-fuel": "Auto, RV, marine fuel, and roadside help.",
    "shopping-essentials": "Groceries, retail, and everyday essentials.",
}

_EDITORIAL_FOOTERS: dict[str, str] = {
    "eat-drink": (
        "Eat & Drink on Hava is curated for Lake Havasu locals — from quick lunches "
        "to dock-and-dine nights. Listings update as we verify hours and details."
    ),
    "on-the-water": (
        "On-the-water listings highlight launches, rentals, and services tied to "
        "Lake Havasu recreation."
    ),
    "home-property-services": (
        "Home & property pros are ranked with verified-first defaults where available."
    ),
    "health-wellness-care": (
        "Health & wellness entries favor verified providers and nearby options."
    ),
    "auto-rv-fuel": (
        "Auto & RV surfaces mobile-service-friendly picks when we have that signal."
    ),
    "shopping-essentials": (
        "Shopping & essentials blends grocery anchors with neighborhood retail."
    ),
}

_EAT_DRINK_CUISINE_CHIPS: tuple[Chip, ...] = (
    Chip("mexican", "Mexican"),
    Chip("bbq", "BBQ"),
    Chip("pizza", "Pizza"),
    Chip("cafes", "Cafés"),
    Chip("bars", "Bars"),
    Chip("bakery", "Bakery"),
    Chip("seafood", "Seafood"),
    Chip("brunch", "Brunch"),
)

_PLACEHOLDER_TRADE_CHIPS: tuple[Chip, ...] = (
    Chip("browse", "Browse listings"),
)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _district_rows(db: Session) -> list[tuple[str, str]]:
    rows = db.execute(select(District.slug, District.name).order_by(District.display_order)).all()
    return [(str(s), str(n)) for s, n in rows]


def _needles_for_cuisine(cuisine_slug: str) -> frozenset[str]:
    c = cuisine_slug.strip().lower()
    table: dict[str, frozenset[str]] = {
        "mexican": frozenset({"mexican", "mexican_restaurant", "taco"}),
        "bbq": frozenset({"bbq", "barbecue", "barbecue_restaurant", "steak"}),
        "pizza": frozenset({"pizza", "pizza_restaurant"}),
        "cafes": frozenset({"cafe", "coffee", "coffee_shop", "tea"}),
        "bars": frozenset({"bar", "pub", "wine_bar", "night_club"}),
        "bakery": frozenset({"bakery", "baked_goods"}),
        "seafood": frozenset({"seafood", "seafood_restaurant", "fish"}),
        "brunch": frozenset({"breakfast", "brunch", "breakfast_restaurant"}),
    }
    return table.get(c, frozenset({c.replace("-", "_")}))


def _provider_matches_cuisine(provider: Provider | None, cuisine_slug: str) -> bool:
    if provider is None:
        return False
    needles = _needles_for_cuisine(cuisine_slug)
    primary = (provider.google_primary_category or "").lower()
    for n in needles:
        if n and n in primary:
            return True
    cats = provider.google_categories or []
    if isinstance(cats, list):
        for gc in cats:
            gl = str(gc).lower()
            for n in needles:
                if n and n in gl:
                    return True
    leg = (provider.category or "").lower()
    for n in needles:
        if n and n in leg.replace("-", "_"):
            return True
    attrs = provider.attributes or {}
    subs = attrs.get("sub_trades")
    if isinstance(subs, list):
        for s in subs:
            sl = str(s).lower()
            for n in needles:
                if n and n in sl:
                    return True
    return False


def _segment_open_close(seg: dict[str, Any]) -> tuple[time | None, time | None]:
    ot = _parse_hours_time(str(seg.get("open") or ""))
    ct = _parse_hours_time(str(seg.get("close") or ""))
    return ot, ct


def _provider_open_past_hour(provider: Provider, hour: int, minute: int = 0) -> bool:
    struct = provider_queries.effective_hours_structured(provider)
    if not struct:
        return False
    target = time(hour, minute)
    for _day, segs in struct.items():
        if not isinstance(segs, list):
            continue
        for seg in segs:
            if not isinstance(seg, dict):
                continue
            ot, ct = _segment_open_close(seg)
            if ot is None or ct is None:
                continue
            if ct <= ot:
                return True
            if ct >= target:
                return True
    return False


def _provider_brunch_window(provider: Provider) -> bool:
    struct = provider_queries.effective_hours_structured(provider)
    if not struct:
        return False
    brunch_start, brunch_end = time(10, 0), time(14, 0)
    for day_key in ("saturday", "sunday"):
        segs = struct.get(day_key)
        if not isinstance(segs, list):
            continue
        for seg in segs:
            if not isinstance(seg, dict):
                continue
            ot, ct = _segment_open_close(seg)
            if ot is None or ct is None:
                continue
            if ot < brunch_end and ct > brunch_start:
                return True
    return False


def _distance_km_for_entity(ent: Entity, ref_lat: float, ref_lng: float) -> float:
    loc = ent.location
    if loc is None or loc.lat is None or loc.lng is None:
        return 9e6
    return _haversine_km(ref_lat, ref_lng, float(loc.lat), float(loc.lng))


def _sort_entity_ids(
    entities: list[Entity],
    *,
    sort_key: str,
    ref_lat: float,
    ref_lng: float,
    db: Session,
) -> list[Entity]:
    if not entities:
        return []
    eids = [e.id for e in entities]
    prov_by_eid = {
        p.entity_id: p for p in db.scalars(select(Provider).where(Provider.entity_id.in_(eids))).all()
    }

    def editorial_key(e: Entity) -> tuple:
        p = prov_by_eid.get(e.id)
        feat = bool(e.featured) or bool(p and p.featured)
        ver = bool(p and p.verified)
        return (not feat, not ver, (e.name or "").lower())

    def top_rated_key(e: Entity) -> tuple:
        p = prov_by_eid.get(e.id)
        rating = float(p.google_rating) if p and p.google_rating is not None else -1.0
        return (-rating, (e.name or "").lower())

    if sort_key == "alphabetical":
        return sorted(entities, key=lambda e: (e.name or "").lower())
    if sort_key == "top_rated":
        return sorted(entities, key=top_rated_key)
    if sort_key == "editorial_pick":
        return sorted(entities, key=editorial_key)
    return sorted(
        entities,
        key=lambda e: (_distance_km_for_entity(e, ref_lat, ref_lng), (e.name or "").lower()),
    )


def _select_entities_for_category(
    db: Session,
    *,
    category_slug: str,
    district_slug: str | None,
    dock_only: bool,
) -> list[Entity]:
    stmt = (
        select(Entity)
        .join(EntityCategory, EntityCategory.entity_id == Entity.id)
        .join(Category, Category.id == EntityCategory.category_id)
        .outerjoin(
            Provider,
            (Provider.entity_id == Entity.id) & (Entity.entity_type == ENTITY_TYPE_COMMERCIAL),
        )
        .options(joinedload(Entity.location), joinedload(Entity.district))
        .where(
            Entity.is_active.is_(True),
            Category.slug == category_slug,
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
    if district_slug and district_slug.strip():
        stmt = stmt.join(District, District.id == Entity.district_id).where(
            District.slug == district_slug.strip().lower()
        )
    if dock_only:
        stmt = stmt.where(Entity.boat_access.isnot(None))

    rows = db.scalars(stmt).unique().all()
    return list(rows)


def _apply_python_filters(
    entities: list[Entity],
    *,
    db: Session,
    category_slug: str,
    cuisine: str | None,
    open_now: bool,
    late_night: bool,
    brunch_only: bool,
    now: datetime,
) -> list[Entity]:
    if not entities:
        return []
    eids = [e.id for e in entities]
    prov_map = {
        p.entity_id: p
        for p in db.scalars(select(Provider).where(Provider.entity_id.in_(eids))).all()
    }

    out: list[Entity] = []
    for ent in entities:
        prov = prov_map.get(ent.id)
        if category_slug == "eat-drink" and cuisine and cuisine.strip():
            if not _provider_matches_cuisine(prov, cuisine.strip()):
                continue
        if open_now:
            if prov is None:
                continue
            is_o, _ = is_open_now(prov, now=now)
            if is_o is not True:
                continue
        if late_night:
            if prov is None or not _provider_open_past_hour(prov, 21):
                continue
        if brunch_only:
            if prov is None or not _provider_brunch_window(prov):
                continue
        out.append(ent)
    return out


def _normalize_sort(raw: str | None, *, category_slug: str) -> str:
    allowed = {"closest_now", "alphabetical", "top_rated", "editorial_pick"}
    default = DEFAULT_SORT_BY_SLUG.get(category_slug, "closest_now")
    if not raw or str(raw).strip().lower() not in allowed:
        return default
    return str(raw).strip().lower()


@router.get("/category/{slug}", response_class=HTMLResponse)
def category_landing(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
    cuisine: str | None = Query(None),
    district: str | None = Query(None),
    open_now_q: str | None = Query(None, alias="open"),
    late: str | None = Query(None),
    brunch: str | None = Query(None),
    dock: str | None = Query(None),
    sort: str | None = Query(None),
) -> HTMLResponse:
    cat_slug = slug.strip().lower()
    if cat_slug not in TIER_1_CATEGORY_SLUGS:
        raise HTTPException(status_code=404, detail="unknown_category")

    now = now_lake_havasu()
    if now.tzinfo is None:
        now = now.replace(tzinfo=LAKE_HAVASU_TZ)

    category_label = CATEGORY_LABELS.get(cat_slug, cat_slug.replace("-", " ").title())
    sort_key = _normalize_sort(sort, category_slug=cat_slug)

    dock_only = dock is not None and str(dock).strip() in {"1", "true", "yes"}
    open_now = open_now_q is not None and str(open_now_q).strip().lower() == "now"
    late_night = late is not None and str(late).strip() == "1"
    brunch_only = brunch is not None and str(brunch).strip() == "1"

    district_slug_filter = district.strip().lower() if district and district.strip() else None

    entities = _select_entities_for_category(
        db,
        category_slug=cat_slug,
        district_slug=district_slug_filter,
        dock_only=dock_only,
    )
    entities = _apply_python_filters(
        entities,
        db=db,
        category_slug=cat_slug,
        cuisine=cuisine,
        open_now=open_now,
        late_night=late_night,
        brunch_only=brunch_only,
        now=now,
    )
    entities = _sort_entity_ids(
        entities,
        sort_key=sort_key,
        ref_lat=_REF_LAT,
        ref_lng=_REF_LNG,
        db=db,
    )

    organic_stream = []
    for ent in entities:
        vm = provider_queries.build_card_view_model(db, ent.id, now=now)
        if vm is not None:
            organic_stream.append(vm)

    district_options = _district_rows(db)

    if cat_slug == "eat-drink":
        cuisine_chips = list(_EAT_DRINK_CUISINE_CHIPS)
    else:
        cuisine_chips = list(_PLACEHOLDER_TRADE_CHIPS)

    operational_defs = [
        {"param": "open", "value": "now", "label": "Open now"},
        {"param": "late", "value": "1", "label": "Open past 9pm"},
        {"param": "brunch", "value": "1", "label": "Brunch"},
        {"param": "dock", "value": "1", "label": "Dock-and-dine"},
    ]

    sort_options = [
        ("closest_now", "Closest now"),
        ("alphabetical", "Alphabetical"),
        ("top_rated", "Top-rated"),
        ("editorial_pick", "Editorial pick"),
    ]

    def cat_href(**kwargs: str | None) -> str:
        q = dict(request.query_params)
        for key, val in kwargs.items():
            if val is None:
                q.pop(key, None)
            else:
                q[key] = str(val)
        tail = urlencode(sorted(q.items()))
        return request.url.path + ("?" + tail if tail else "")

    ctx = {
        "cat_href": cat_href,
        "today_label": now.strftime("%A, %B ") + str(now.day),
        "category_slug": cat_slug,
        "category_label": category_label,
        "category_one_liner": _CATEGORY_ONE_LINERS.get(cat_slug, "Browse trusted local listings."),
        "cuisine_chips": cuisine_chips,
        "district_chips": [Chip(s, n) for s, n in district_options],
        "operational_chips": operational_defs,
        "active_cuisine": (cuisine or "").strip().lower() or None,
        "active_district": district_slug_filter,
        "active_open_now": open_now,
        "active_late": late_night,
        "active_brunch": brunch_only,
        "active_dock": dock_only,
        "sort_options": sort_options,
        "sort_current": sort_key,
        "organic_stream": organic_stream,
        "show_sparse_banner": len(organic_stream) < 15,
        "editorial_footer_text": _EDITORIAL_FOOTERS.get(cat_slug, ""),
        "ref_lat": _REF_LAT,
        "ref_lng": _REF_LNG,
    }

    return templates.TemplateResponse(
        request=request,
        name="category_landing.html",
        context=ctx,
    )
