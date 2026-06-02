"""Itinerary builder routes (Lane B5).

  * ``GET /plan``          — HTML itinerary page (Lake Light styling).
  * ``POST /api/plan``     — structured JSON itinerary for programmatic use.

Both draw from :func:`app.plan.builder.build_itinerary`, which assembles the
plan from real catalog data only. The three-tier chat router and the intent
layer are untouched — this is an additive surface.
"""

from __future__ import annotations

from datetime import time
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.provider_name import register_template_filters, register_template_globals
from app.db.database import get_db
from app.plan.builder import Itinerary, Stop, build_itinerary

router = APIRouter(tags=["plan"])

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)


class PlanRequest(BaseModel):
    when: str | None = None
    area: str | None = None


def _fmt(t: time) -> str:
    suffix = "AM" if t.hour < 12 else "PM"
    h12 = t.hour % 12 or 12
    return f"{h12}:{t.minute:02d} {suffix}" if t.minute else f"{h12} {suffix}"


def _stop_to_dict(stop: Stop) -> dict:
    pick = None
    if stop.pick is not None:
        pick = {
            "kind": stop.pick.kind,
            "name": stop.pick.name,
            "href": stop.pick.href,
            "detail": stop.pick.detail,
            "note": stop.pick.note,
        }
    return {
        "slot": stop.slot,
        "label": stop.label,
        "suggested_time": _fmt(stop.suggested_time),
        "filled": stop.filled,
        "pick": pick,
        "empty_message": stop.empty_message if not stop.filled else "",
        "contribute_href": stop.contribute_href,
    }


def _itinerary_to_dict(it: Itinerary) -> dict:
    return {
        "plan_date": it.plan_date.isoformat(),
        "title": it.title,
        "filled_count": it.filled_count,
        "all_empty": it.all_empty,
        "stops": [_stop_to_dict(s) for s in it.stops],
    }


@router.get("/plan", response_class=HTMLResponse)
def plan_page(
    request: Request,
    when: str | None = None,
    area: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    itinerary = build_itinerary(db, when=when, area=area)
    return templates.TemplateResponse(
        request=request,
        name="plan.html",
        context={"itinerary": itinerary},
    )


@router.post("/api/plan")
def api_plan(
    body: PlanRequest,
    db: Session = Depends(get_db),
) -> JSONResponse:
    itinerary = build_itinerary(db, when=body.when, area=body.area)
    return JSONResponse(content=_itinerary_to_dict(itinerary))
