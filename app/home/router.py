"""Hava -- ``GET /home`` route.

Direction C lane: serves the dark-chrome ``home_c.html`` by default
(PR D6 cutover -- the redesign is now the production home page).
The legacy ``home.html`` only renders when the operator explicitly opts
out via ``HOME_REDESIGN=0`` env var or ``?redesign=0`` query override.

Rollback path: set ``HOME_REDESIGN=0`` on Railway. No code change, no
revert. The legacy template is still wired here for that exact reason.

Direction A's PR #5 also wired ``base["redesign"]`` into ``home.html`` to
toggle Marquee/Supporters/etc. inside the same template. Direction C
supersedes Direction A: the flag now switches templates entirely. We keep
``base["redesign"] = False`` on the legacy path so any A-era template
conditionals stay off when the flag is off.

Mock-data leak gate (HAVA_DEMO_MODE): when off (default in prod), the
legacy path's per-row fallback to mock content is suppressed. With the
gate off, an empty DB row yields an empty list, which the template's
``{% for ... %}`` loop quietly skips. With the gate on (demos, screenshots,
template development), the prior behavior is preserved.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.chat.disclosure_render import DISCLOSURE_WORD
from app.conditions.view_model import build_conditions_strip_view_model
from app.core.timezone import now_lake_havasu
from app.db.database import get_db
from app.db.models import User
from app.home import (
    browse_tiles,
    demo_mode,
    feature_flags,
    mock_data,
    queries,
    queries_c,
    snowbird_panel,
    sponsor_store,
)

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(tags=["home"])

# Hand-picked hero image for D1 (Bridgewater Channel sunset).
# D2 will swap this for a curated rotation tied to time of day + season.
_D1_HERO_IMAGE = (
    "https://images.unsplash.com/photo-1502082553048-f009c37129b9"
    "?w=1800&q=85&auto=format&fit=crop"
)


def _empty_context() -> dict:
    """Return the minimum keys home.html needs when mock_data is off.

    Mirrors the SHAPE of mock_data.build_context() but every row is empty.
    The legacy template's ``{% for ... %}`` loops render nothing for empty
    lists; section headers stay visible but bodies collapse gracefully.
    """
    today = now_lake_havasu()
    return {
        "today_label": today.strftime("%A, %B ") + str(today.day),
        "tonight_label": "Tonight" if today.hour >= 16 else "Today",
        "added_month": today.strftime("%B"),
        "chips": [],
        "tonight": [],
        "this_week": [],
        "this_week_total": 0,
        "new_on_hava": [],
        "spotlights": [],
        "categories": [],
    }


@router.get("/home", response_class=HTMLResponse)
def serve_home(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> HTMLResponse:
    """Render /home -- Direction C when flag is on, legacy when off."""

    redesign = feature_flags.home_redesign_enabled(
        request.query_params.get("redesign"),
    )

    if redesign:
        # ---- Direction C path (D1: chrome scaffold, D2: Discover grid,
        #      D3: Eat & drink scroll row, D4: Services grid) ----
        now = now_lake_havasu()
        discover_cards = queries_c.discover_grid(db, now=now)
        eat_cards = queries_c.eat_row(db, now=now)
        service_cards = queries_c.services_grid(db)
        return templates.TemplateResponse(
            request=request,
            name="home_c.html",
            context={
                "today_label": now.strftime("%A, %B ") + str(now.day),
                "now_label": now.strftime("%I:%M %p").lstrip("0"),
                "hero_image_url": _D1_HERO_IMAGE,
                "discover_cards": discover_cards,
                "eat_cards": eat_cards,
                "service_cards": service_cards,
                # D5 shared topbar partial reads ``active_tab`` to apply
                # the ``is-active`` class. ``today`` -> Today pill lights
                # up; the four category pills stay inert hyperlinks.
                "active_tab": "today",
            },
        )

    # ---- Legacy path (PR #5 layout, mock-gate aware) ----
    if demo_mode.demo_mode_enabled():
        base = mock_data.build_context()
    else:
        base = _empty_context()

    base["disclosure_word"] = DISCLOSURE_WORD
    base["redesign"] = False  # Direction A conditionals stay off in prod.

    # Live row reads. With HAVA_DEMO_MODE off (default), an empty DB
    # leaves these rows empty rather than falling back to mock content.
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
    base["categories"] = live_categories or base["categories"]

    # Sponsor slot: live record OR None (renders the fallback card).
    base["sponsor"] = sponsor_store.get_active_sponsor(db)

    panel_ctx = snowbird_panel.build_snowbird_panel_context(
        db, current_user=current_user
    )
    base["snowbird_panel"] = snowbird_panel.snowbird_panel_template_dict(panel_ctx)
    base["browse_tiles"] = browse_tiles.build_browse_tiles(db)
    base["conditions_strip"] = build_conditions_strip_view_model(db)

    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context=base,
    )
