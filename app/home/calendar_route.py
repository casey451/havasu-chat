"""``GET /calendar`` — the v4 glanceable month grid + agenda.

The discovery destination the concierge intent-router sends people to.
``?cal=YYYY-MM`` drives month nav; ``?date=YYYY-MM-DD`` selects the agenda day
(server-rendered, no JS needed).

2026-07-02 flag collapse: the pre-v4 ``calendar_lake.html`` list view (and its
free-text/segmented filter params) was deleted with the HOME_REDESIGN flag —
v4 had been permanently on in prod since ~06-23. The old filter params are
still accepted-and-ignored so bookmarked links don't 422.

``noindex``: ``/events-ui`` is the indexable events surface; ``/calendar`` is a
personalized utility view.
"""

from __future__ import annotations

from datetime import date as dt_date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.templates import make_templates
from app.core.timezone import now_lake_havasu
from app.db.database import get_db
from app.home import redesign
from app.home.sandstone import parse_cal_param

router = APIRouter(tags=["calendar"])

templates = make_templates()


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
    # Pre-v4 list-view filter params, accepted so old links don't 422.
    del q, aud, age, part, type_, days
    now = now_lake_havasu()
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
    return resp
