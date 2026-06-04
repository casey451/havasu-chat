"""Tier 1 category landing pages (Phase 6.2).

GET /category/<slug> renders the shared shell + organic Hava card stream.
Eat & Drink is the first proof category; other Tier 1 slugs reuse the template.

This singular ``/category/`` surface co-exists with the plural
``/categories/`` surface in ``app/categories/router.py`` (PR D5).
PR D6 (2026-05-26) documented the split rather than collapsing them:

  /category/{slug}    (THIS module, singular)
    SEO landing pages and intent-led narrowing. ~12 Tier-1 slugs with
    sub-trade chips, operational chips, ranking modes (closest_now /
    editorial_pick), and per-slug DEFAULT_SORT_BY_SLUG. Entity /
    EntityCategory-backed, ~1150 LoC.

  /categories/{slug}  (app/categories/router.py, plural)
    Direction C chrome-driven nav. 5 mega-category routes that
    aggregate multiple Provider.category slugs. No filter chips
    (BUILD.md rule). Provider.category-backed, ~77 LoC template.

When slugs overlap (eat-drink, on-the-water, pets, ...) the routes
intentionally serve different UX: plural is the chrome-led "show me
everything"; singular is the SEO landing with filter narrowing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.conditions_temperature import read_current_temperature_f
from app.core.liveness import liveness_dampener
from app.core.provider_name import register_template_filters, register_template_globals
from app.core.ranking import CardRankInput, compute_card_rank
from app.core.timezone import LAKE_HAVASU_TZ, now_lake_havasu
from app.db.database import get_db
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import Category, District, Entity, EntityCategory, Provider
from app.events import series as event_series
from app.events.queries import event_window_for_chip, events_in_window
from app.home.queries import CATEGORY_LABELS
from app.providers import queries as provider_queries
from app.providers.queries import _parse_hours_time, is_open_now

router = APIRouter(tags=["category"])

_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)


@dataclass(frozen=True)
class Chip:
    slug: str
    label: str


@dataclass(frozen=True)
class CategoryPageConfig:
    sub_trade_chips: tuple[Chip, ...]
    operational_chips: tuple[dict[str, str], ...]
    sort_default: str


TIER_1_CATEGORY_SLUGS: frozenset[str] = frozenset(
    {
        "eat-drink",
        "on-the-water",
        "home-property-services",
        "health-wellness-care",
        "auto-rv-fuel",
        "shopping-essentials",
        "events",
        "outdoors-parks-trails",
        "classes-sports-recreation",
        "lodging-vacation-rentals",
        "pets",
        "public-civic-resources",
    }
)

# Anonymous default anchor — Lake Havasu City approximate civic center.
REF_LAT = 34.4839
REF_LNG = -114.3225
_REF_LAT = REF_LAT
_REF_LNG = REF_LNG

DEFAULT_SORT_BY_SLUG: dict[str, str] = {
    "eat-drink": "closest_now",
    "on-the-water": "closest_now",
    "home-property-services": "editorial_pick",
    "health-wellness-care": "closest_now",
    "auto-rv-fuel": "closest_now",
    "shopping-essentials": "closest_now",
    "events": "chronological",
    "outdoors-parks-trails": "closest_now",
    "classes-sports-recreation": "closest_now",
    "lodging-vacation-rentals": "closest_now",
    "pets": "closest_now",
    "public-civic-resources": "closest_now",
}

_CATEGORY_ONE_LINERS: dict[str, str] = {
    "eat-drink": "Restaurants, cafés, bars, and local flavors.",
    "on-the-water": "Marinas, launches, rentals, and lake life.",
    "home-property-services": "Trusted pros for your home and property.",
    "health-wellness-care": "Care, wellness, and fitness around town.",
    "auto-rv-fuel": "Auto, RV, marine fuel, and roadside help.",
    "shopping-essentials": "Groceries, retail, and everyday essentials.",
    "events": "Festivals, venues, and things happening around town.",
    "outdoors-parks-trails": "Parks, trails, golf, and outdoor recreation.",
    "classes-sports-recreation": "Classes, sports, childcare, and recreation.",
    "lodging-vacation-rentals": "Hotels, resorts, and vacation stays.",
    "pets": "Pet stores, groomers, trainers, and pet services.",
    "public-civic-resources": "Libraries, transit, visitor info, and civic services.",
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
    "auto-rv-fuel": ("Auto & RV surfaces mobile-service-friendly picks when we have that signal."),
    "shopping-essentials": (
        "Shopping & essentials blends grocery anchors with neighborhood retail."
    ),
    "events": (
        "Events on Hava surfaces venues and happenings — from live music to seasonal festivals."
    ),
    "outdoors-parks-trails": (
        "Parks and trails around Lake Havasu — state parks, city parks, and golf."
    ),
    "classes-sports-recreation": ("Classes and recreation for kids, sports, and active locals."),
    "lodging-vacation-rentals": ("Lodging from waterfront resorts to vacation rentals."),
    "pets": ("Pet services and supplies for Lake Havasu pet owners."),
    "public-civic-resources": ("Public and civic resources residents rely on year-round."),
}

_CATEGORY_PAGE_CONFIG: dict[str, CategoryPageConfig] = {
    "eat-drink": CategoryPageConfig(
        sub_trade_chips=(
            Chip("mexican", "Mexican"),
            Chip("bbq", "BBQ"),
            Chip("pizza", "Pizza"),
            Chip("cafes", "Cafés"),
            Chip("bars", "Bars"),
            Chip("bakery", "Bakery"),
            Chip("seafood", "Seafood"),
            Chip("brunch", "Brunch"),
        ),
        operational_chips=(
            {"param": "open", "value": "now", "label": "Open now"},
            {"param": "late", "value": "1", "label": "Open past 9pm"},
            {"param": "brunch", "value": "1", "label": "Brunch"},
            {"param": "dock", "value": "1", "label": "Dock-and-dine"},
        ),
        sort_default="closest_now",
    ),
    "on-the-water": CategoryPageConfig(
        sub_trade_chips=(
            Chip("marinas", "Marinas"),
            Chip("boat-rentals", "Boat rentals"),
            Chip("lake-tours", "Lake tours"),
            Chip("watersports", "Watersports"),
            Chip("fishing-charters", "Fishing charters"),
            Chip("beaches", "Beaches"),
            Chip("launches", "Launches"),
        ),
        operational_chips=(
            {"param": "open", "value": "now", "label": "Open now"},
            {"param": "boat", "value": "1", "label": "Boat-friendly"},
            {"param": "family", "value": "1", "label": "Family-friendly"},
            {"param": "free", "value": "1", "label": "Free"},
            {"param": "paid", "value": "1", "label": "Paid"},
        ),
        sort_default="closest_now",
    ),
    "home-property-services": CategoryPageConfig(
        sub_trade_chips=(
            Chip("plumber", "Plumber"),
            Chip("electrician", "Electrician"),
            Chip("hvac", "HVAC"),
            Chip("handyman", "Handyman"),
            Chip("landscaper", "Landscaper"),
            Chip("pool-service", "Pool service"),
            Chip("cleaning", "Cleaning"),
            Chip("pest-control", "Pest control"),
            Chip("roofer", "Roofer"),
            Chip("garage-door", "Garage door"),
        ),
        operational_chips=(
            {"param": "open", "value": "now", "label": "Open now"},
            {"param": "verified", "value": "1", "label": "Verified"},
            {"param": "mobile", "value": "1", "label": "Mobile-service"},
            {"param": "emergency", "value": "1", "label": "Emergency 24h"},
        ),
        sort_default="editorial_pick",
    ),
    "health-wellness-care": CategoryPageConfig(
        sub_trade_chips=(
            Chip("doctor", "Doctor"),
            Chip("dentist", "Dentist"),
            Chip("urgent-care", "Urgent care"),
            Chip("pharmacy", "Pharmacy"),
            Chip("vet", "Vet"),
            Chip("gym", "Gym"),
            Chip("yoga", "Yoga"),
            Chip("massage", "Massage"),
            Chip("chiropractor", "Chiropractor"),
            Chip("mental-health", "Mental health"),
        ),
        operational_chips=(
            {"param": "open", "value": "now", "label": "Open now"},
            {"param": "npi", "value": "1", "label": "NPI-verified"},
            {"param": "new-patients", "value": "1", "label": "Accepting new patients"},
            {"param": "insurance", "value": "1", "label": "Insurance accepted"},
        ),
        sort_default="closest_now",
    ),
    "auto-rv-fuel": CategoryPageConfig(
        sub_trade_chips=(
            Chip("auto-repair", "Auto repair"),
            Chip("tire-shop", "Tire shop"),
            Chip("rv-repair", "RV repair"),
            Chip("rv-park", "RV park"),
            Chip("gas-station", "Gas station"),
            Chip("car-wash", "Car wash"),
            Chip("detailing", "Detailing"),
            Chip("mobile-mechanic", "Mobile mechanic"),
        ),
        operational_chips=(
            {"param": "open", "value": "now", "label": "Open now"},
            {"param": "mobile", "value": "1", "label": "Mobile-service"},
            {"param": "tow", "value": "1", "label": "Tow available"},
            {"param": "rv", "value": "1", "label": "RV-friendly"},
        ),
        sort_default="closest_now",
    ),
    "shopping-essentials": CategoryPageConfig(
        sub_trade_chips=(
            Chip("grocery", "Grocery"),
            Chip("pharmacy", "Pharmacy"),
            Chip("hardware", "Hardware"),
            Chip("sporting-goods", "Sporting goods"),
            Chip("pet-supplies", "Pet supplies"),
            Chip("clothing", "Clothing"),
            Chip("department-store", "Department store"),
            Chip("liquor", "Liquor"),
            Chip("bakery", "Bakery"),
            Chip("specialty", "Specialty"),
        ),
        operational_chips=(
            {"param": "open", "value": "now", "label": "Open now"},
            {"param": "late", "value": "1", "label": "Open past 9pm"},
            {"param": "drive", "value": "1", "label": "Drive-through"},
            {"param": "curbside", "value": "1", "label": "Curbside pickup"},
        ),
        sort_default="closest_now",
    ),
    "events": CategoryPageConfig(
        sub_trade_chips=(
            Chip("event-venues", "Event venues"),
            Chip("live-music", "Live music"),
            Chip("art-galleries", "Art galleries"),
            Chip("museums", "Museums"),
            Chip("movie-theaters", "Movie theaters"),
            Chip("bowling", "Bowling"),
            Chip("arcades", "Arcades"),
        ),
        operational_chips=(
            {"param": "when", "value": "today", "label": "Today"},
            {"param": "when", "value": "this-weekend", "label": "This weekend"},
            {"param": "when", "value": "this-week", "label": "This week"},
            {"param": "when", "value": "next-month", "label": "Next month"},
        ),
        sort_default="chronological",
    ),
    "outdoors-parks-trails": CategoryPageConfig(
        sub_trade_chips=(
            Chip("parks", "Parks"),
            Chip("golf-courses", "Golf courses"),
            Chip("mini-golf", "Mini golf"),
            Chip("trails", "Trails"),
            Chip("beaches", "Beaches"),
            Chip("viewpoints", "Viewpoints"),
            Chip("campgrounds", "Campgrounds"),
        ),
        operational_chips=(
            {"param": "open", "value": "now", "label": "Open now"},
            {"param": "free", "value": "1", "label": "Free"},
            {"param": "family", "value": "1", "label": "Family-friendly"},
            {"param": "dog", "value": "1", "label": "Dog-friendly"},
            {"param": "seasonal", "value": "1", "label": "Seasonal access"},
        ),
        sort_default="closest_now",
    ),
    "classes-sports-recreation": CategoryPageConfig(
        sub_trade_chips=(
            Chip("yoga", "Yoga"),
            Chip("pilates", "Pilates"),
            Chip("swim", "Swim"),
            Chip("pickleball", "Pickleball"),
            Chip("childcare", "Childcare"),
            Chip("youth_sports", "Youth sports"),
            Chip("adult_sports", "Adult sports"),
        ),
        operational_chips=(
            {"param": "drop_in", "value": "1", "label": "Drop-in OK"},
            {"param": "registration", "value": "1", "label": "Registration required"},
            {"param": "kids", "value": "1", "label": "Kids (0-12)"},
            {"param": "teens", "value": "1", "label": "Teens (13-17)"},
            {"param": "adults", "value": "1", "label": "Adults (18+)"},
            {"param": "55_plus", "value": "1", "label": "55+"},
        ),
        sort_default="closest_now",
    ),
    "lodging-vacation-rentals": CategoryPageConfig(
        sub_trade_chips=(
            Chip("hotels", "Hotels"),
            Chip("motels", "Motels"),
            Chip("resorts", "Resorts"),
            Chip("vacation-rentals", "Vacation rentals"),
            Chip("bed-breakfast", "Bed & breakfast"),
        ),
        operational_chips=(
            {"param": "open", "value": "now", "label": "Open now"},
            {"param": "waterfront", "value": "1", "label": "Waterfront"},
            {"param": "pool", "value": "1", "label": "Pool"},
            {"param": "pet", "value": "1", "label": "Pet-friendly"},
            {"param": "parking", "value": "1", "label": "Free parking"},
        ),
        sort_default="closest_now",
    ),
    "pets": CategoryPageConfig(
        sub_trade_chips=(
            Chip("pet-stores", "Pet stores"),
            Chip("dog-groomers", "Dog groomers"),
            Chip("dog-boarding", "Dog boarding"),
            Chip("dog-trainers", "Dog trainers"),
            Chip("veterinary", "Veterinary"),
        ),
        operational_chips=(
            {"param": "open", "value": "now", "label": "Open now"},
            {"param": "walkins", "value": "1", "label": "Walk-ins"},
            {"param": "mobile", "value": "1", "label": "Mobile service"},
            {"param": "emergency", "value": "1", "label": "Emergency"},
        ),
        sort_default="closest_now",
    ),
    "public-civic-resources": CategoryPageConfig(
        sub_trade_chips=(
            Chip("library", "Library"),
            Chip("transit", "Transit"),
            Chip("visitor-info", "Visitor info"),
            Chip("utilities", "Utilities"),
            Chip("airport", "Airport"),
            Chip("senior-resources", "Senior resources"),
            Chip("payment-licensing", "Payment & licensing"),
            Chip("civic-orgs", "Civic orgs"),
        ),
        operational_chips=(
            {"param": "open", "value": "now", "label": "Open now"},
            {"param": "free", "value": "1", "label": "Free"},
            {"param": "appointment", "value": "1", "label": "Appointment required"},
            {"param": "always", "value": "1", "label": "24/7 access"},
        ),
        sort_default="closest_now",
    ),
}


def category_page_config(slug: str) -> CategoryPageConfig:
    return _CATEGORY_PAGE_CONFIG.get(slug, _CATEGORY_PAGE_CONFIG["eat-drink"])


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


def _needles_for_trade(trade_slug: str) -> frozenset[str]:
    c = trade_slug.strip().lower().replace("-", "_")
    return frozenset({c, c.replace("_", " ")})


def _provider_matches_trade(provider: Provider | None, trade_slug: str) -> bool:
    if provider is None:
        return False
    needles = _needles_for_trade(trade_slug)
    primary = (provider.google_primary_category or "").lower()
    for n in needles:
        if n and n in primary.replace("-", "_"):
            return True
    cats = provider.google_categories or []
    if isinstance(cats, list):
        for gc in cats:
            gl = str(gc).lower()
            for n in needles:
                if n and n in gl.replace("-", "_"):
                    return True
    leg = (provider.category or "").lower()
    for n in needles:
        if n and n in leg.replace("-", "_"):
            return True
    attrs = provider.attributes or {}
    subs = attrs.get("sub_trades")
    if isinstance(subs, list):
        for s in subs:
            sl = str(s).lower().replace("-", "_")
            for n in needles:
                if n and n in sl:
                    return True
    return False


def _entity_boat_friendly(ent: Entity) -> bool:
    ba = ent.boat_access
    if ba is None:
        return False
    if isinstance(ba, dict):
        return bool(ba)
    return True


def _provider_attr_flag(provider: Provider | None, key: str) -> bool:
    if provider is None:
        return False
    attrs = provider.attributes or {}
    return bool(attrs.get(key))


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
    category_slug: str,
    now: datetime,
) -> list[Entity]:
    if not entities:
        return []
    eids = [e.id for e in entities]
    prov_by_eid = {
        p.entity_id: p
        for p in db.scalars(select(Provider).where(Provider.entity_id.in_(eids))).all()
    }

    def editorial_key(e: Entity) -> tuple:
        p = prov_by_eid.get(e.id)
        feat = bool(e.featured) or bool(p and p.featured)
        ver = bool(p and p.verified)
        return (not feat, not ver, (e.name or "").lower())

    def top_rated_key(e: Entity) -> tuple:
        p = prov_by_eid.get(e.id)
        rating = float(p.google_rating) if p and p.google_rating is not None else -1.0
        if rating >= 0:
            # Liveness dampener — bury stale listings in Top-rated too. Same
            # entity-first fallback and NULL → no-op semantics as the
            # closest_now path (see rank_inputs_for_category).
            liveness = (
                e.liveness_score
                if e.liveness_score is not None
                else (p.liveness_score if p is not None else None)
            )
            rating *= liveness_dampener(liveness)
        return (-rating, (e.name or "").lower())

    if sort_key == "alphabetical":
        return sorted(entities, key=lambda e: (e.name or "").lower())
    if sort_key == "top_rated":
        return sorted(entities, key=top_rated_key)
    if sort_key == "editorial_pick":
        return sorted(entities, key=editorial_key)
    if sort_key == "closest_now":
        rank_inp = rank_inputs_for_category(
            entities,
            category_slug=category_slug,
            ref_lat=ref_lat,
            ref_lng=ref_lng,
            prov_by_eid=prov_by_eid,
            now=now,
        )

        temp_f = read_current_temperature_f(db)

        def closest_key(e: Entity) -> tuple:
            inp = rank_inp[e.id]
            score = compute_card_rank(inp, now=now, temperature_f=temp_f)
            return (-score, (e.name or "").lower())

        return sorted(entities, key=closest_key)
    return sorted(
        entities,
        key=lambda e: (_distance_km_for_entity(e, ref_lat, ref_lng), (e.name or "").lower()),
    )


def rank_inputs_for_category(
    entities: list[Entity],
    *,
    category_slug: str,
    ref_lat: float,
    ref_lng: float,
    prov_by_eid: dict[str, Provider],
    now: datetime,
) -> dict[str, CardRankInput]:
    out: dict[str, CardRankInput] = {}
    verified_boost = 0.15
    open_boost = 0.10
    boat_boost = 0.12
    mobile_boost = 0.10
    if category_slug == "health-wellness-care":
        verified_boost = 0.25
    if category_slug in (
        "shopping-essentials",
        "outdoors-parks-trails",
        "pets",
        "public-civic-resources",
    ):
        open_boost = 0.18
    if category_slug == "on-the-water":
        boat_boost = 0.20
    if category_slug == "auto-rv-fuel":
        mobile_boost = 0.18
    for ent in entities:
        p = prov_by_eid.get(ent.id)
        is_open: bool | None = None
        if p is not None:
            is_open, _ = is_open_now(p, now=now)
        elif ent.entity_type != ENTITY_TYPE_COMMERCIAL:
            is_open, _ = provider_queries.is_open_status_for_entity(ent, now=now)
        out[ent.id] = CardRankInput(
            distance_km=_distance_km_for_entity(ent, ref_lat, ref_lng),
            name=ent.name or "",
            heat_exposure=ent.heat_exposure,
            verified=bool(p and p.verified),
            is_open_now=is_open,
            boat_access_populated=ent.boat_access is not None,
            mobile_service=bool(
                ent.is_mobile_service or (p and _provider_attr_flag(p, "mobile_service"))
            ),
            verified_boost=verified_boost,
            open_now_boost=open_boost,
            boat_access_boost=boat_boost,
            mobile_service_boost=mobile_boost,
            # Liveness dampener — buries stale Google-sourced listings. Prefer the
            # entity's synced score; fall back to the Provider's. NULL → no
            # dampening, so non-Google entities are unaffected.
            liveness_score=(
                ent.liveness_score
                if ent.liveness_score is not None
                else (p.liveness_score if p is not None else None)
            ),
        )
    return out


def select_entities_for_categories(
    db: Session,
    *,
    category_slugs: list[str],
    district_slug: str | None,
    boat_only: bool,
) -> list[Entity]:
    if not category_slugs:
        return []
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
            joinedload(Entity.district),
            joinedload(Entity.categories).joinedload(EntityCategory.category),
        )
        .where(
            Entity.is_active.is_(True),
            Category.slug.in_(category_slugs),
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
    if boat_only:
        stmt = stmt.where(Entity.boat_access.isnot(None))

    rows = db.scalars(stmt).unique().all()
    return list(rows)


def _select_entities_for_category(
    db: Session,
    *,
    category_slug: str,
    district_slug: str | None,
    dock_only: bool,
) -> list[Entity]:
    return select_entities_for_categories(
        db,
        category_slugs=[category_slug],
        district_slug=district_slug,
        boat_only=dock_only,
    )


def _apply_python_filters(
    entities: list[Entity],
    *,
    db: Session,
    category_slug: str,
    cuisine: str | None,
    trade: str | None,
    open_now: bool,
    late_night: bool,
    brunch_only: bool,
    verified_only: bool,
    mobile_only: bool,
    boat_only: bool,
    free_only: bool,
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
        elif trade and trade.strip():
            if not _provider_matches_trade(prov, trade.strip()):
                continue
        if open_now:
            if prov is not None:
                is_o, _ = is_open_now(prov, now=now)
                if is_o is not True:
                    continue
            else:
                is_o, _ = provider_queries.is_open_status_for_entity(ent, now=now)
                if is_o is not True:
                    continue
        if late_night:
            if prov is None or not _provider_open_past_hour(prov, 21):
                continue
        if brunch_only:
            if prov is None or not _provider_brunch_window(prov):
                continue
        if verified_only and not (prov and prov.verified):
            continue
        if mobile_only and not (
            ent.is_mobile_service or (prov and _provider_attr_flag(prov, "mobile_service"))
        ):
            continue
        if boat_only and not _entity_boat_friendly(ent):
            continue
        if free_only:
            attrs = (prov.attributes if prov else {}) or {}
            if not attrs.get("free_admission") and not attrs.get("free"):
                continue
        out.append(ent)
    return out


def _programs_for_entities(db: Session, entity_ids: list[str]) -> dict[str, list]:
    from app.db.models import Program

    if not entity_ids:
        return {}
    rows = db.scalars(
        select(Program).where(
            Program.entity_id.in_(entity_ids),
            Program.is_active.is_(True),
        )
    ).all()
    out: dict[str, list] = {}
    for prog in rows:
        out.setdefault(prog.entity_id, []).append(prog)
    return out


def _program_matches_age_band(prog, band: str) -> bool:
    amin = prog.age_min
    amax = prog.age_max
    if amin is None and amax is None:
        return False
    amin = int(amin) if amin is not None else 0
    amax = int(amax) if amax is not None else 99
    if band == "kids":
        return amin <= 12 and amax >= 0
    if band == "teens":
        return amin <= 17 and amax >= 13
    if band == "adults":
        return amax >= 18
    if band == "55_plus":
        return amin >= 55 or amax >= 55
    return False


def _crowd_notes_flag(notes: object, key: str) -> bool | None:
    if not isinstance(notes, dict):
        return None
    val = notes.get(key)
    if val is True:
        return True
    if val is False:
        return False
    return None


def _apply_classes_sports_filters(
    entities: list[Entity],
    *,
    db: Session,
    drop_in: bool,
    registration: bool,
    kids: bool,
    teens: bool,
    adults: bool,
    senior_55: bool,
) -> list[Entity]:
    if not any((drop_in, registration, kids, teens, adults, senior_55)):
        return entities
    eids = [e.id for e in entities]
    prog_map = _programs_for_entities(db, eids)
    out: list[Entity] = []
    for ent in entities:
        notes = ent.crowd_notes
        if drop_in:
            flag = _crowd_notes_flag(notes, "drop_in_friendly")
            if flag is not True:
                continue
        if registration:
            flag = _crowd_notes_flag(notes, "drop_in_friendly")
            if flag is not False:
                continue
        progs = prog_map.get(ent.id, [])
        if kids and not any(_program_matches_age_band(p, "kids") for p in progs):
            continue
        if teens and not any(_program_matches_age_band(p, "teens") for p in progs):
            continue
        if adults and not any(_program_matches_age_band(p, "adults") for p in progs):
            continue
        if senior_55 and not any(_program_matches_age_band(p, "55_plus") for p in progs):
            continue
        out.append(ent)
    return out


def _normalize_sort(raw: str | None, *, category_slug: str) -> str:
    allowed = {
        "closest_now",
        "alphabetical",
        "top_rated",
        "editorial_pick",
        "chronological",
        "featured",
    }
    default = DEFAULT_SORT_BY_SLUG.get(category_slug, "closest_now")
    if category_slug == "events":
        allowed = {
            "chronological",
            "closest_now",
            "featured",
            "alphabetical",
            "top_rated",
            "editorial_pick",
        }
    if not raw or str(raw).strip().lower() not in allowed:
        return default
    return str(raw).strip().lower()


def _build_events_category_stream(
    db: Session,
    *,
    when: str | None,
    sort_key: str,
    ref_lat: float,
    ref_lng: float,
    now: datetime,
    limit: int = 50,
) -> list:
    """Event-typed Hava cards for /category/events with RRULE expansion."""
    today = now.date()
    if when and when.strip():
        win_start, win_end = event_window_for_chip(when.strip(), today=today)
    else:
        win_start, win_end = today, today + timedelta(days=30)

    flat = events_in_window(
        db,
        window_start=win_start,
        window_end=win_end,
        category_slug="events",
        limit=limit * 3,
    )
    # Collapse recurring series (e.g. daily Lap Swim) to a single card on their
    # next occurrence — same de-flooding as the home/events feeds (P0 Task 4).
    # Sort chronologically first so the kept occurrence is the earliest in-window
    # one; dedup on the series key, not event.id (occurrences are distinct rows).
    flat = sorted(flat, key=lambda p: (p[1], p[0].start_time))
    seen: set[tuple[str, str, str]] = set()
    pairs: list[tuple] = []
    for event, occ_date in flat:
        key = event_series.series_key(
            event.normalized_title, event.location_normalized, event.start_time
        )
        if key in seen:
            continue
        seen.add(key)
        pairs.append((event, occ_date))
        if len(pairs) >= limit:
            break

    if sort_key == "chronological":
        pairs.sort(key=lambda p: (p[1], p[0].start_time, p[0].normalized_title))
    elif sort_key == "featured":
        pairs.sort(
            key=lambda p: (
                not bool(p[0].featured),
                p[1],
                p[0].start_time,
            )
        )
    elif sort_key == "closest_now":
        eids = [p[0].entity_id for p in pairs]
        entities = list(db.scalars(select(Entity).where(Entity.id.in_(eids))).all()) if eids else []
        prov_by_eid = (
            {
                pr.entity_id: pr
                for pr in db.scalars(select(Provider).where(Provider.entity_id.in_(eids))).all()
            }
            if eids
            else {}
        )
        rank_inp = rank_inputs_for_category(
            entities,
            category_slug="events",
            ref_lat=ref_lat,
            ref_lng=ref_lng,
            prov_by_eid=prov_by_eid,
            now=now,
        )
        temp_f = read_current_temperature_f(db)

        def closest_key(pair: tuple) -> tuple:
            inp = rank_inp.get(pair[0].entity_id)
            score = compute_card_rank(inp, now=now, temperature_f=temp_f) if inp else 0.0
            return (-score, pair[1], pair[0].normalized_title)

        pairs.sort(key=closest_key)
    else:
        pairs.sort(key=lambda p: (p[0].title or "").lower())

    stream = []
    for event, occ_date in pairs:
        vm = provider_queries.build_card_view_model_for_event_occurrence(
            db, event.id, occ_date, now=now
        )
        if vm is not None:
            stream.append(vm)
    return stream


@router.get("/category/{slug}", response_class=HTMLResponse)
def category_landing(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
    cuisine: str | None = Query(None),
    trade: str | None = Query(None),
    district: str | None = Query(None),
    open_now_q: str | None = Query(None, alias="open"),
    late: str | None = Query(None),
    brunch: str | None = Query(None),
    dock: str | None = Query(None),
    verified: str | None = Query(None),
    mobile: str | None = Query(None),
    boat: str | None = Query(None),
    free: str | None = Query(None),
    sort: str | None = Query(None),
    when: str | None = Query(None),
    drop_in: str | None = Query(None, alias="drop_in"),
    registration: str | None = Query(None),
    kids: str | None = Query(None),
    teens: str | None = Query(None),
    adults: str | None = Query(None),
    senior_55: str | None = Query(None, alias="55_plus"),
) -> HTMLResponse:
    cat_slug = slug.strip().lower()
    if cat_slug not in TIER_1_CATEGORY_SLUGS:
        raise HTTPException(status_code=404, detail="unknown_category")

    now = now_lake_havasu()
    if now.tzinfo is None:
        now = now.replace(tzinfo=LAKE_HAVASU_TZ)

    category_label = CATEGORY_LABELS.get(cat_slug, cat_slug.replace("-", " ").title())
    page_cfg = category_page_config(cat_slug)
    sort_key = _normalize_sort(sort, category_slug=cat_slug)

    def _flag(val: str | None) -> bool:
        return val is not None and str(val).strip() in {"1", "true", "yes"}

    dock_only = _flag(dock) or _flag(boat)
    open_now = open_now_q is not None and str(open_now_q).strip().lower() == "now"
    late_night = _flag(late)
    brunch_only = _flag(brunch)
    verified_only = _flag(verified)
    mobile_only = _flag(mobile)
    free_only = _flag(free)

    district_slug_filter = district.strip().lower() if district and district.strip() else None
    active_trade = (cuisine or trade or "").strip().lower() or None

    if cat_slug == "events":
        organic_stream = _build_events_category_stream(
            db,
            when=when,
            sort_key=sort_key,
            ref_lat=_REF_LAT,
            ref_lng=_REF_LNG,
            now=now,
        )
    else:
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
            trade=trade,
            open_now=open_now,
            late_night=late_night,
            brunch_only=brunch_only,
            verified_only=verified_only,
            mobile_only=mobile_only,
            boat_only=dock_only,
            free_only=free_only,
            now=now,
        )
        if cat_slug == "classes-sports-recreation":
            entities = _apply_classes_sports_filters(
                entities,
                db=db,
                drop_in=_flag(drop_in),
                registration=_flag(registration),
                kids=_flag(kids),
                teens=_flag(teens),
                adults=_flag(adults),
                senior_55=_flag(senior_55),
            )
        entities = _sort_entity_ids(
            entities,
            sort_key=sort_key,
            ref_lat=_REF_LAT,
            ref_lng=_REF_LNG,
            db=db,
            category_slug=cat_slug,
            now=now,
        )

        organic_stream = []
        for ent in entities:
            vm = provider_queries.build_card_view_model(db, ent.id, now=now)
            if vm is not None:
                organic_stream.append(vm)

    district_options = _district_rows(db)
    cuisine_chips = list(page_cfg.sub_trade_chips)
    operational_defs = list(page_cfg.operational_chips)

    if cat_slug == "events":
        sort_options = [
            ("chronological", "Chronological"),
            ("closest_now", "Closest now"),
            ("featured", "Featured"),
            ("alphabetical", "Alphabetical"),
        ]
    else:
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
        "map_scope_slug": cat_slug,
        "boat_mode_active": dock_only,
        "category_slug": cat_slug,
        "category_label": category_label,
        "category_one_liner": _CATEGORY_ONE_LINERS.get(cat_slug, "Browse trusted local listings."),
        "cuisine_chips": cuisine_chips,
        "district_chips": [Chip(s, n) for s, n in district_options],
        "operational_chips": operational_defs,
        "active_cuisine": active_trade if cat_slug == "eat-drink" else None,
        "active_trade": active_trade if cat_slug != "eat-drink" else None,
        "active_district": district_slug_filter,
        "active_open_now": open_now,
        "active_late": late_night,
        "active_brunch": brunch_only,
        "active_dock": dock_only,
        "active_verified": verified_only,
        "active_mobile": mobile_only,
        "active_free": free_only,
        "active_when": when.strip().lower() if when and when.strip() else None,
        "active_drop_in": _flag(drop_in),
        "active_registration": _flag(registration),
        "active_kids": _flag(kids),
        "active_teens": _flag(teens),
        "active_adults": _flag(adults),
        "active_55_plus": _flag(senior_55),
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
