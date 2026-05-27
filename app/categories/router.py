"""Hava -- ``GET /categories/{slug}`` route.

Direction C category-page lane (PR D5). Sister surface to
``app/home/router.py`` -- shares the dark cinematic chrome from
``home_c.html`` but renders a category-specific grid below a slim
header (no full hero). The 12 D4 service tiles and the 4 home_c
mega-tab anchors all resolve here.

Co-exists with ``app/api/routes/category_pages.py``'s
``/category/{slug}`` (singular) Phase 6.2 surface. Different URL,
different data model, different rendering -- intentional during
dogfooding. D6 / a future PR decides which surface wins.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.categories import queries as cat_queries
from app.core.timezone import now_lake_havasu
from app.db.database import get_db

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

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
