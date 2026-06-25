"""``GET /calendar`` — the customized events+classes calendar (Phase 2b).

The discovery destination the concierge intent-router sends people to. Renders
the lake calendar from real per-day events+classes (``calendar_view``), filtered
by a free-text query + segmented controls (all links — fully server-rendered).

``noindex`` during the dark rollout: ``/events-ui`` is the indexable events
surface; ``/calendar`` is a personalized utility view. The Phase-8 flip removes
the noindex.
"""

from __future__ import annotations

from datetime import date as dt_date
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.provider_name import register_template_filters, register_template_globals
from app.core.timezone import now_lake_havasu
from app.db.database import get_db
from app.home import flags, redesign
from app.home.calendar_view import build_calendar
from app.home.sandstone import parse_cal_param

router = APIRouter(tags=["calendar"])

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)


@router.get("/calendar", response_class=HTMLResponse)
def serve_calendar(
    request: Request,
    q: str = "",
    aud: str = "",
    age: str = "",
    part: str = "",
    type_: str = Query("", alias="type"),
    days: str = "",
    cal_param: str = Query("", alias="cal"),
    date: str = "",
    db: Session = Depends(get_db),
) -> HTMLResponse:
    now = now_lake_havasu()

    # ── home_redesign (dark): the v4 glanceable month grid + agenda, served only
    # when the flag resolves on. The existing /calendar list stays intact below for
    # instant rollback. ``?cal=YYYY-MM`` drives month nav; ``?date=YYYY-MM-DD``
    # selects the agenda day (server-rendered, no JS needed).
    if flags.home_redesign_enabled(request):
        year, month = parse_cal_param(cal_param or None, default=now)
        selected: dt_date | None = None
        try:
            selected = dt_date.fromisoformat(date) if date else None
        except ValueError:
            selected = None
        view = redesign.calendar_month_view(
            db, year=year, month=month, today=now.date(), selected=selected, now=now
        )
        resp = templates.TemplateResponse(
            request=request,
            name="calendar_redesign.html",
            context={
                "cal": view,
                "today_label": now.strftime("%A, %B ") + str(now.day),
                "cond_tiles": redesign.conditions_tiles(db, now=now),
                "gas": redesign.gas_top5(db, now=now),
                "active_tab": "today",
            },
        )
        resp.headers["X-Robots-Tag"] = "noindex"
        flags.apply_preview_cookie(request, resp)
        return resp

    cal = build_calendar(
        db, q=q, aud=aud, age=age, part=part, type_=type_, days_param=days,
        today=now.date(), now=now,
    )
    response = templates.TemplateResponse(
        request=request, name="calendar_lake.html", context={"cal": cal}
    )
    response.headers["X-Robots-Tag"] = "noindex"
    return response
