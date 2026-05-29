"""Hava -- ``GET /home`` route (Direction C / ``home_c.html``).

Also hosts the sponsor attribution endpoints (v52 P0):

* ``GET /sponsor/click`` — bumps ``Sponsor.clicks`` and 302s to the row's
  ``cta_url``. Linked from ``_partials/marquee.html``. Without this route,
  every marquee CTA 404s.
* ``GET /sponsor`` — advertiser landing stub. Linked from the marquee unsold
  fallback and from the home/category footers.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.analytics import record_event
from app.core.provider_name import register_template_filters, register_template_globals
from app.core.rate_limit import limiter
from app.core.timezone import now_lake_havasu
from app.db.database import get_db
from app.db.models import AdSlot, Sponsor
from app.home import pullquote, queries_c, sponsor_store

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)

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


# Sponsor attribution endpoints (v52 P0 — see module docstring) ----------------


def _parse_slot(slot: str) -> AdSlot:
    """Validate the ``slot`` query param against the four-tier enum."""
    try:
        return AdSlot(slot)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid sponsor slot") from exc


@router.get("/sponsor/click")
@limiter.limit("60/minute")
def sponsor_click(
    request: Request,
    id: str,
    slot: str = "marquee",
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Attribute a sponsor click, then 302 to the booked ``cta_url``.

    GET (not POST) because the template uses a plain ``<a href>`` — switching
    to POST would force JS or a form, neither of which fits the editorial card
    design. Open-redirect-safe because ``cta_url`` is admin-curated at insert
    time and we only redirect when the row matches the live filter (approved +
    active + within booking window).
    """
    ad_slot = _parse_slot(slot)
    row = (
        sponsor_store._live_filter_for_slot(db.query(Sponsor), ad_slot)
        .filter(Sponsor.id == id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    # Atomic UPDATE — single statement, no row lock needed for ++ counter.
    db.execute(
        update(Sponsor).where(Sponsor.id == row.id).values(clicks=Sponsor.clicks + 1)
    )
    db.commit()
    # v54 Track B — long-form click event. ``home.spotlight.click`` fires
    # only when the slot is spotlight (cleanest downstream join with the
    # ``home.spotlight.impression`` rows from sponsor_store.active_spotlights).
    # ``home.sponsor.click`` fires for every slot so cross-tier CTR roll-ups
    # don't need a UNION. Best-effort: ``record_event`` swallows DB errors.
    if ad_slot is AdSlot.SPOTLIGHT:
        record_event(
            db,
            "home.spotlight.click",
            slot=ad_slot.value,
            sponsor_id=row.id,
            ranking_score=row.weight,
        )
    record_event(
        db,
        "home.sponsor.click",
        slot=ad_slot.value,
        sponsor_id=row.id,
        ranking_score=row.weight,
    )
    # 302 (not 301) — never cache the redirect; CTA URLs can rotate.
    return RedirectResponse(url=row.cta_url, status_code=302)


@router.get("/sponsor", response_class=HTMLResponse)
def sponsor_landing(request: Request) -> HTMLResponse:
    """Advertiser landing page. Static stub for v52; copy lands in a follow-up.

    Linked from ``home_c.html`` / ``category_c.html`` footers and from the
    marquee unsold-fallback. Was a 404 before this PR.
    """
    return templates.TemplateResponse(
        request=request,
        name="sponsor_landing.html",
        context={},
    )
