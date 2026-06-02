"""Weekend-digest opt-in + follow-venue routes (Phase A3).

Self-contained router, separate from the alerts router (sibling-lane owned).
All endpoints require an authenticated user. The opt-in is explicit: a
``DigestSubscription`` row exists only after the user opts in (no
auto-enrollment), and toggling off flips ``enabled`` rather than deleting.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as SqlSession

from app.auth.dependencies import get_current_user
from app.auth.favorites import (
    entity_is_followable_venue,
    follow_venue,
    unfollow_venue,
)
from app.db.database import get_db
from app.db.models import DigestSubscription, Entity

router = APIRouter(tags=["digest"])


class FollowVenueBody(BaseModel):
    entity_id: str


class DigestOptInBody(BaseModel):
    enabled: bool = True


def _require_user(request: Request):
    return get_current_user(request)


@router.post("/api/venues/follow")
def api_follow_venue(
    request: Request,
    body: FollowVenueBody,
    db: SqlSession = Depends(get_db),
) -> JSONResponse:
    user = _require_user(request)
    if user is None:
        return JSONResponse(status_code=401, content={"detail": "login_required"})
    ent = db.get(Entity, body.entity_id)
    if ent is None:
        return JSONResponse(status_code=404, content={"detail": "entity_not_found"})
    if not entity_is_followable_venue(ent.entity_type):
        return JSONResponse(status_code=400, content={"detail": "not_a_venue"})
    action = follow_venue(db, user.id, body.entity_id)
    db.commit()
    return JSONResponse(content={"action": action, "following": True})


@router.post("/api/venues/unfollow")
def api_unfollow_venue(
    request: Request,
    body: FollowVenueBody,
    db: SqlSession = Depends(get_db),
) -> JSONResponse:
    user = _require_user(request)
    if user is None:
        return JSONResponse(status_code=401, content={"detail": "login_required"})
    action = unfollow_venue(db, user.id, body.entity_id)
    db.commit()
    return JSONResponse(content={"action": action, "following": False})


@router.get("/api/digest/subscription")
def api_digest_subscription_get(
    request: Request, db: SqlSession = Depends(get_db)
) -> JSONResponse:
    user = _require_user(request)
    if user is None:
        return JSONResponse(status_code=401, content={"detail": "login_required"})
    sub = db.scalars(
        select(DigestSubscription).where(
            DigestSubscription.user_id == user.id,
            DigestSubscription.delivery_channel == "email",
        )
    ).first()
    enabled = bool(sub is not None and sub.enabled)
    return JSONResponse(content={"opted_in": enabled})


@router.post("/api/digest/subscription")
def api_digest_subscription_set(
    request: Request,
    body: DigestOptInBody,
    db: SqlSession = Depends(get_db),
) -> JSONResponse:
    user = _require_user(request)
    if user is None:
        return JSONResponse(status_code=401, content={"detail": "login_required"})
    sub = db.scalars(
        select(DigestSubscription).where(
            DigestSubscription.user_id == user.id,
            DigestSubscription.delivery_channel == "email",
        )
    ).first()
    if sub is None:
        # Honor an explicit opt-out with no prior row by simply not creating one.
        if not body.enabled:
            db.commit()
            return JSONResponse(content={"opted_in": False})
        sub = DigestSubscription(user_id=user.id, delivery_channel="email", enabled=True)
        db.add(sub)
    else:
        sub.enabled = body.enabled
        sub.updated_at = datetime.now(UTC)
    db.commit()
    return JSONResponse(content={"opted_in": bool(body.enabled)})
