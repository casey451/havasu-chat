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

from app.auth.dependencies import get_current_user
from app.chat.disclosure_render import DISCLOSURE_WORD
from app.core.timezone import now_lake_havasu
from app.db.database import get_db
from app.db.models import User
from app.home import browse_tiles, mock_data, queries, snowbird_panel, sponsor_store

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(tags=["home"])


@router.get("/home", response_class=HTMLResponse)
def serve_home(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> HTMLResponse:
    """Render /home with live catalog data + per-row mock fallbacks."""
    base = mock_data.build_context()
    base["disclosure_word"] = DISCLOSURE_WORD

    # Live row reads. Fall back to the mocked equivalent per-row when the
    # DB returns empty (catalog still being populated).
    live_tonight = queries.tonight(db)
    live_this_week = queries.this_week(db)
    live_new = queries.new_on_hava(db)
    live_spotlights = queries.spotlights(db)
    live_categories = queries.categories(db)

    base["tonight_label"] = queries.tonight_or_today_label(now_lake_havasu())
    base["tonight"] = live_tonight or base["tonight"]
    base["this_week"] = live_this_week or base["this_week"]
    base["this_week_total"] = queries.this_week_total(db) or base["this_week_total"]
    base["new_on_hava"] = live_new or base["new_on_hava"]
    base["spotlights"] = live_spotlights or base["spotlights"]
    base["categories"] = live_categories  # builder has its own fallback

    # Sponsor slot: live record OR None (renders the fallback card).
    base["sponsor"] = sponsor_store.get_active_sponsor(db)

    panel_ctx = snowbird_panel.build_snowbird_panel_context(
        db, current_user=current_user
    )
    base["snowbird_panel"] = snowbird_panel.snowbird_panel_template_dict(panel_ctx)
    base["browse_tiles"] = browse_tiles.build_browse_tiles(db)

    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context=base,
    )
