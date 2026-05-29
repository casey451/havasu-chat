"""Hava -- ``GET /categories/{slug}`` route.

Direction C category-page lane (PR D5). Sister surface to
``app/home/router.py`` -- shares the dark cinematic chrome from
``home_c.html`` but renders a category-specific grid below a slim
header (no full hero). The 12 D4 service tiles and the 4 home_c
mega-tab anchors all resolve here.

Two category surfaces live in the codebase. PR D6 (2026-05-26)
resolved them as a *deliberate editorial split*, not duplicates to
reconcile:

  /categories/{slug}  (THIS module, plural)
    Chrome-driven nav. Tap a topbar tab on /home -> land here.
    5 mega-category routes (today / eat-drink / on-the-water /
    things-to-do / services) that aggregate multiple
    Provider.category slugs into a single editorial grid. No filter
    chips per BUILD.md's "no filters in chrome / chat" rule.
    Provider.category-backed, ~77 LoC template.

  /category/{slug}    (app/api/routes/category_pages.py, singular)
    SEO landing pages and intent-led narrowing. ~12 Tier-1 slugs
    (plumbers, electricians, eat-drink, on-the-water, pets, ...)
    with filter chips and sub-trade refinement. Entity / EntityCategory
    backed, ~1150 LoC template, ranked by closest_now / editorial_pick.

When the slugs overlap (eat-drink, on-the-water, pets, etc.) the
two routes intentionally serve different UX -- the funnel is:
chrome tab -> /categories/services -> tap a tile -> /category/plumbers.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.categories import queries as cat_queries
from app.core.provider_name import register_template_filters, register_template_globals
from app.core.timezone import now_lake_havasu
from app.db.database import get_db

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)

router = APIRouter(tags=["categories"])


@router.get("/categories/{slug}", response_class=HTMLResponse)
def serve_category(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Render a single category page.

    Returns 404 when the slug is not in
    ``app.categories.queries.CATEGORY_FILTERS``. Otherwise, renders
    ``category_c.html`` with a filtered Provider list, a slim header,
    and the shared topbar with the right tab marked active.
    """
    normalised = (slug or "").strip().lower()
    if not cat_queries.is_valid_category_slug(normalised):
        raise HTTPException(status_code=404, detail="unknown_category")

    now = now_lake_havasu()
    label, one_liner = cat_queries.CATEGORY_DISPLAY[normalised]
    count = cat_queries.category_count(db, normalised)
    cards = cat_queries.category_cards(db, normalised, now=now)
    active_tab = cat_queries.active_tab_for(normalised)

    return templates.TemplateResponse(
        request=request,
        name="category_c.html",
        context={
            "today_label": now.strftime("%A, %B ") + str(now.day),
            "now_label": now.strftime("%I:%M %p").lstrip("0"),
            "category_slug": normalised,
            "category_label": label,
            "category_one_liner": one_liner,
            "category_count": count,
            "category_cards": cards,
            "active_tab": active_tab,
        },
    )
