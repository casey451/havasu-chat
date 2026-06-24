"""Account alert subscription UI (Phase 8a)."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as SqlSession

from app.alerts.thresholds import ALERT_TYPES_V1, EVENT_TRAFFIC_DEFERRED
from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import AlertSubscription

router = APIRouter(tags=["account-alerts"])

_VALID_TYPES = frozenset((*ALERT_TYPES_V1, EVENT_TRAFFIC_DEFERRED))


def _templates():
    from pathlib import Path

    from fastapi.templating import Jinja2Templates

    from app.core.provider_name import register_template_filters, register_template_globals

    t = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))
    register_template_filters(t)
    register_template_globals(t)
    return t


@router.get("/account/alerts", response_class=HTMLResponse)
def account_alerts_get(request: Request, db: SqlSession = Depends(get_db)) -> HTMLResponse:
    user = get_current_user(request)
    if user is None:
        return RedirectResponse(
            url=f"/login?next={quote('/account/alerts', safe='')}",
            status_code=303,
        )
    subs = list(
        db.scalars(
            select(AlertSubscription).where(
                AlertSubscription.user_id == user.id,
                AlertSubscription.delivery_channel == "email",
            )
        ).all()
    )
    active = {s.alert_type for s in subs}
    return _templates().TemplateResponse(
        request=request,
        name="account_alerts_lake.html",
        context={
            "user": user,
            "active_types": active,
            "alert_types": ALERT_TYPES_V1,
            "event_traffic_deferred": EVENT_TRAFFIC_DEFERRED,
            "saved": request.query_params.get("saved") == "1",
        },
    )


@router.post("/account/alerts", response_class=HTMLResponse)
def account_alerts_post(
    request: Request,
    db: SqlSession = Depends(get_db),
    heat_advisory: str | None = Form(default=None),
    aqi_alert: str | None = Form(default=None),
    lake_hazard: str | None = Form(default=None),
    snooze_until: str | None = Form(default=None),
) -> RedirectResponse:
    user = get_current_user(request)
    if user is None:
        return RedirectResponse(
            url=f"/login?next={quote('/account/alerts', safe='')}",
            status_code=303,
        )

    opted_in = set()
    if heat_advisory:
        opted_in.add("heat_advisory")
    if aqi_alert:
        opted_in.add("aqi_alert")
    if lake_hazard:
        opted_in.add("lake_hazard")

    existing = list(
        db.scalars(
            select(AlertSubscription).where(
                AlertSubscription.user_id == user.id,
                AlertSubscription.delivery_channel == "email",
            )
        ).all()
    )
    existing_types = {s.alert_type: s for s in existing}

    for alert_type in opted_in:
        if alert_type not in _VALID_TYPES or alert_type == EVENT_TRAFFIC_DEFERRED:
            continue
        if alert_type not in existing_types:
            db.add(
                AlertSubscription(
                    id=str(uuid4()),
                    user_id=user.id,
                    alert_type=alert_type,
                    delivery_channel="email",
                )
            )

    for alert_type, sub in existing_types.items():
        if alert_type not in opted_in:
            db.delete(sub)

    paused: datetime | None = None
    if snooze_until and snooze_until.strip():
        try:
            paused = datetime.fromisoformat(snooze_until.strip()).replace(tzinfo=None)
        except ValueError:
            paused = None

    if paused is not None:
        for sub in db.scalars(
            select(AlertSubscription).where(AlertSubscription.user_id == user.id)
        ).all():
            sub.paused_until = paused

    db.commit()
    return RedirectResponse(url="/account/alerts?saved=1", status_code=303)
