"""Hava -- ``GET /home`` route (Direction C / ``home_c.html``)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.provider_name import register_template_filters
from app.core.timezone import now_lake_havasu
from app.db.database import get_db
from app.home import pullquote, queries_c

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)

router = APIRouter(tags=["home"])

_HERO_UNSPLASH_SIZE = "?w=1800&q=85&auto=format&fit=crop"

_HERO_ROTATION: tuple[dict[str, str], ...] = (
    {
        "id": "photo-jp9Bdu6IGq4",
        "photographer": "Susan Weber",
        "profile_url": "https://unsplash.com/@havasuartist",
    },
    {
        "id": "photo-UbhT7o0Q0S0",
        "photographer": "Nick LaRovere",
        "profile_url": "https://unsplash.com/@nicklarovere",
    },
    {
        "id": "photo-ZDw4bMLSUXA",
        "photographer": "Steve Gribble",
        "profile_url": "https://unsplash.com/@steve_g_",
    },
    {
        "id": "photo-8y9aDTeYqvU",
        "photographer": "Royce Fonseca",
        "profile_url": "https://unsplash.com/@casunshine0508",
    },
    {
        "id": "photo-QS-aTbuoJFc",
        "photographer": "Spencer Davis",
        "profile_url": "https://unsplash.com/@spencerdavis",
    },
    {
        "id": "photo-o2s4ALzj_ks",
        "photographer": "NIR HIMI",
        "profile_url": "https://unsplash.com/@nirhimi",
    },
)


def _hero_image_url(photo_id: str) -> str:
    return f"https://images.unsplash.com/{photo_id}{_HERO_UNSPLASH_SIZE}"


def _pick_hero(now: datetime) -> dict[str, str]:
    """Return today's hero entry with a sized Unsplash URL."""
    entry = _HERO_ROTATION[now.date().toordinal() % len(_HERO_ROTATION)]
    return {
        "id": entry["id"],
        "photographer": entry["photographer"],
        "profile_url": entry["profile_url"],
        "url": _hero_image_url(entry["id"]),
    }


@router.get("/home", response_class=HTMLResponse)
def serve_home(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Render /home — dark-chrome Direction C template."""
    now = now_lake_havasu()
    hero = _pick_hero(now)
    discover_cards = queries_c.discover_grid(db, now=now)
    eat_cards = queries_c.eat_row(db, now=now)
    service_cards = queries_c.services_grid(db)
    return templates.TemplateResponse(
        request=request,
        name="home_c.html",
        context={
            "today_label": now.strftime("%A, %B ") + str(now.day),
            "now_label": now.strftime("%I:%M %p").lstrip("0"),
            "hero_image_url": hero["url"],
            "hero_attribution": {
                "photographer": hero["photographer"],
                "profile_url": hero["profile_url"],
            },
            "discover_cards": discover_cards,
            "eat_cards": eat_cards,
            "service_cards": service_cards,
            "active_tab": "today",
            "hava_read": pullquote.get_quote(db),
        },
    )
