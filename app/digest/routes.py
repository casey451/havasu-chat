"""Weekend-digest opt-in + follow-venue routes (Phase A3).

Self-contained router, separate from the alerts router (sibling-lane owned).
All endpoints require an authenticated user. The opt-in is explicit: a
``DigestSubscription`` row exists only after the user opts in (no
auto-enrollment), and toggling off flips ``enabled`` rather than deleting.
"""

from __future__ import annotations

import os
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


def _digest_signups_enabled() -> bool:
    """Whether the weekend-digest opt-in accepts NEW subscriptions.

    OFF by default (2026-07-03): the digest builder + render exist but no sender
    is wired — there is no send cron — so accepting an opt-in would promise a
    delivery we never make. Gated so we don't collect emails we can't fulfil.
    Flip ``FEATURE_FLAG_WEEKEND_DIGEST=true`` once the sender ships. Opt-OUT is
    always honored regardless of this flag (an existing subscriber can turn off).
    """
    return os.environ.get("FEATURE_FLAG_WEEKEND_DIGEST", "").strip().lower() == "true"


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
    # ``available`` tells a future opt-in UI whether sign-ups are live (a sender
    # is wired) so it can hide/disable the toggle honestly.
    return JSONResponse(content={"opted_in": enabled, "available": _digest_signups_enabled()})


@router.post("/api/digest/subscription")
def api_digest_subscription_set(
    request: Request,
    body: DigestOptInBody,
    db: SqlSession = Depends(get_db),
) -> JSONResponse:
    user = _require_user(request)
    if user is None:
        return JSONResponse(status_code=401, content={"detail": "login_required"})
    # Opt-IN (and re-enabling) is gated until a sender ships — don't collect a
    # subscription we can't deliver. Opt-OUT falls through so an existing
    # subscriber can always turn off.
    if body.enabled and not _digest_signups_enabled():
        return JSONResponse(content={"opted_in": False, "available": False})
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
