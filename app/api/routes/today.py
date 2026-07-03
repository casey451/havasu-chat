"""GET /today — "Today in Havasu" Lake Light conditions dashboard (Lane A1).

Renders a Lake Light strip (lake level + water temp, wind, AQI, sunset, cheapest
gas) assembled by ``build_today_payload`` over the existing conditions cache.
Honest "Unavailable" states surface when a source is missing or stale.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.conditions.today_payload import build_today_payload
from app.core.rate_limit import limiter, public_html_rate_limit
from app.core.templates import make_templates
from app.core.timezone import format_now_lake_havasu, now_lake_havasu
from app.db.database import get_db

router = APIRouter(tags=["today"])

templates = make_templates()


@router.get("/today", response_class=HTMLResponse)
@limiter.limit(public_html_rate_limit)
def today_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    now = datetime.now(UTC).replace(tzinfo=None)
    payload = build_today_payload(db, now=now)
    return templates.TemplateResponse(
        request=request,
        name="today_lake.html",
        context={
            "fields": payload["fields"],
            "any_available": payload["any_available"],
            "local_time_label": format_now_lake_havasu(now_lake_havasu()),
        },
    )
