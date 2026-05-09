"""Hava — ``GET /home`` route (BUILD.md steps 1-3).

Step 1: static template + mocked data.
Step 2: live Tonight / This week / New on Hava / Local pros / categories
        (per-row mock fallback when the catalog is empty).
Step 3: live editorial sponsor slot from ``sponsors`` table — None when
        no record is active, which renders the "Sponsor this slot →"
        fallback card defined in ``home.html``.

Posture for empty catalog: each row falls back to its mocked equivalent
when the DB returns nothing. The sponsor slot is the exception — when no
sponsor is active, we render the real fallback ("Sponsor this slot"), not
the mocked Havasu Outdoor Co. card.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.home import mock_data, queries, sponsor_store

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(tags=["home"])


@router.get("/home", response_class=HTMLResponse)
def serve_home(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Render /home with live catalog data + per-row mock fallbacks."""
    base = mock_data.build_context()

    # Live row reads. Fall back to the mocked equivalent per-row when the
    # DB returns empty (catalog still being populated).
    live_tonight = queries.tonight(db)
    live_this_week = queries.this_week(db)
    live_new = queries.new_on_hava(db)
    live_spotlights = queries.spotlights(db)
    live_categories = queries.categories(db)

    base["tonight"] = live_tonight or base["tonight"]
    base["tonight_section_label"] = queries.today_section_label()
    base["this_week"] = live_this_week or base["this_week"]
    base["this_week_total"] = queries.this_week_total(db) or base["this_week_total"]
    base["new_on_hava"] = live_new or base["new_on_hava"]
    base["spotlights"] = live_spotlights or base["spotlights"]
    base["categories"] = live_categories  # builder has its own fallback

    # Legacy sponsor slot (back-compat — same record as marquee).
    base["sponsor"] = sponsor_store.get_active_sponsor(db)
    # Phase 2B four-tier inventory (CRITIQUE_AND_REDESIGN.md §B5.6).
    base["marquee"] = sponsor_store.active_marquee(db)
    base["promoted"] = sponsor_store.active_promoted(db)
    base["spotlight_sponsors"] = sponsor_store.active_spotlights(db)
    base["supporters"] = sponsor_store.supporters(db)

    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context=base,
    )
