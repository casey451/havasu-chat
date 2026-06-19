"""Phase 6.4 — themed group landing pages at ``GET /group/<slug>``."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.routes import category_pages as cat_pages
from app.core.provider_name import register_template_filters, register_template_globals
from app.core.timezone import LAKE_HAVASU_TZ, now_lake_havasu
from app.db.database import get_db
from app.groups import themed_groups as tg
from app.groups.themed_group_stream import get_themed_group_card_stream
from app.providers import queries as provider_queries

router = APIRouter(tags=["themed-groups"])

_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)


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
        )
    else:
        entities = cat_pages.select_entities_for_categories(
            db,
            category_slugs=category_slugs,
            district_slug=None,
            boat_only=boat_only,
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
        "active_open_now": False,
        "active_late": False,
        "active_brunch": False,
        "active_dock": boat_only,
        "active_verified": False,
        "active_mobile": False,
        "active_free": False,
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

    _lake = getattr(request.state, "theme", "desert") == "lake"
    return templates.TemplateResponse(
        request=request,
        name="themed_group_landing_lake.html" if _lake else "themed_group_landing.html",
        context=ctx,
    )
