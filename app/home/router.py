"""Hava -- ``GET /home`` route (Direction C / ``home_c.html``)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.timezone import now_lake_havasu
from app.db.database import get_db
from app.home import pullquote, queries_c

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(tags=["home"])

_D1_HERO_IMAGE = (
    "https://images.unsplash.com/photo-1502082553048-f009c37129b9"
    "?w=1800&q=85&auto=format&fit=crop"
)


@router.get("/home", response_class=HTMLResponse)
def serve_home(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Render /home — dark-chrome Direction C template."""
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
            "active_tab": "today",
            "hava_read": pullquote.get_quote(db),
        },
    )
