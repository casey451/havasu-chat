"""Phase 6.4 — themed group landing pages at ``GET /group/<slug>``."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.routes import category_pages as cat_pages
from app.core.templates import make_templates
from app.core.timezone import LAKE_HAVASU_TZ, now_lake_havasu
from app.db.database import get_db
from app.groups import themed_groups as tg
from app.groups.themed_group_stream import get_themed_group_card_stream
from app.providers import queries as provider_queries

router = APIRouter(tags=["themed-groups"])

templates = make_templates()


@router.get("/group/{slug}", response_class=HTMLResponse)
def themed_group_landing(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
    sort: str | None = Query(None),
    boat: str | None = Query(None),
) -> HTMLResponse:
    group_slug = slug.strip().lower()
    category_slugs = tg.get_categories_for_group(group_slug)
    if not category_slugs:
        raise HTTPException(status_code=404, detail="unknown_group")

    now = now_lake_havasu()
    if now.tzinfo is None:
        now = now.replace(tzinfo=LAKE_HAVASU_TZ)

    def _flag(val: str | None) -> bool:
        return val is not None and str(val).strip() in {"1", "true", "yes"}

    boat_only = _flag(boat)
    # Operational + audience filter chips — read from the query string so the chips
    # actually narrow the list (Casey 2026-06-29). Applied below only when at least
    # one is active, so the default (unfiltered) page view is byte-for-byte unchanged.
    drop_in = _flag(request.query_params.get("drop_in"))
    registration = _flag(request.query_params.get("registration"))
    youth = _flag(request.query_params.get("youth"))
    adults = _flag(request.query_params.get("adults"))
    open_now = request.query_params.get("open") == "now"
    late_night = _flag(request.query_params.get("late"))
    brunch_only = _flag(request.query_params.get("brunch"))
    verified_only = _flag(request.query_params.get("verified"))
    mobile_only = _flag(request.query_params.get("mobile"))
    free_only = _flag(request.query_params.get("free"))
    npi_only = _flag(request.query_params.get("npi"))
    when = request.query_params.get("when")
    sort_slug = category_slugs[0]
    sort_key = cat_pages._normalize_sort(sort, category_slug=sort_slug)

    if "events" in category_slugs:
        organic_stream = get_themed_group_card_stream(
            db,
            group_slug,
            limit=30,
            ref_lat=cat_pages.REF_LAT,
            ref_lng=cat_pages.REF_LNG,
            now=now,
            boat_only=boat_only,
            when=when,
        )
    else:
        entities = cat_pages.select_entities_for_categories(
            db,
            category_slugs=category_slugs,
            district_slug=None,
            boat_only=boat_only,
        )
        if "classes-sports-recreation" in category_slugs:
            entities = cat_pages._apply_classes_sports_filters(
                entities,
                db=db,
                drop_in=drop_in,
                registration=registration,
                youth=youth,
                adults=adults,
            )
        # Operational chips (Open now / Verified / Mobile / Free / Late / Brunch).
        # boat_only is already applied at the select layer, so it's not re-passed.
        if any(
            (open_now, late_night, brunch_only, verified_only, mobile_only, free_only, npi_only)
        ):
            entities = cat_pages._apply_python_filters(
                entities,
                db=db,
                category_slug=sort_slug,
                cuisine=None,
                trade=None,
                open_now=open_now,
                late_night=late_night,
                brunch_only=brunch_only,
                verified_only=verified_only,
                mobile_only=mobile_only,
                boat_only=False,
                free_only=free_only,
                npi_only=npi_only,
                now=now,
            )
        entities = cat_pages._sort_entity_ids(
            entities,
            sort_key=sort_key,
            ref_lat=cat_pages.REF_LAT,
            ref_lng=cat_pages.REF_LNG,
            db=db,
            category_slug=sort_slug,
            now=now,
        )
        organic_stream = []
        for ent in entities:
            vm = provider_queries.build_card_view_model(db, ent.id, now=now)
            if vm is not None:
                organic_stream.append(vm)

    page_cfg = cat_pages.category_page_config(sort_slug)
    district_options = cat_pages._district_rows(db)

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
        "group_slug": group_slug,
        "group_label": tg.group_label(group_slug),
        "group_one_liner": tg.group_one_liner(group_slug),
        "group_accent": tg.group_accent(group_slug),
        "category_slugs": category_slugs,
        "category_slug": sort_slug,
        "category_label": tg.group_label(group_slug),
        "category_one_liner": tg.group_one_liner(group_slug),
        "cuisine_chips": list(page_cfg.sub_trade_chips),
        "district_chips": [cat_pages.Chip(s, n) for s, n in district_options],
        "operational_chips": list(page_cfg.operational_chips),
        "active_cuisine": None,
        "active_trade": None,
        "active_district": None,
        "active_open_now": open_now,
        "active_late": late_night,
        "active_brunch": brunch_only,
        "active_dock": boat_only,
        "active_verified": verified_only,
        "active_mobile": mobile_only,
        "active_free": free_only,
        "active_npi": npi_only,
        "active_when": when,
        "active_drop_in": drop_in,
        "active_registration": registration,
        "active_youth": youth,
        "active_adults": adults,
        "sort_options": sort_options,
        "sort_current": sort_key,
        "organic_stream": organic_stream,
        "show_sparse_banner": len(organic_stream) < 15,
        "editorial_footer_text": cat_pages._EDITORIAL_FOOTERS.get(
            sort_slug,
            "Browse trusted local listings on Hava.",
        ),
        "map_scope_slug": group_slug,
        "boat_mode_active": boat_only,
    }

    return templates.TemplateResponse(
        request=request,
        name="themed_group_landing_lake.html",
        context=ctx,
    )
