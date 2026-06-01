"""Admin CRUD JSON for businesses (providers) and events (master spec §4.4)."""

from __future__ import annotations

from datetime import date as date_type
from datetime import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.admin_contributions import require_admin
from app.db.database import get_db
from app.db.entity_dual_write import create_event_and_entity, create_provider_and_entity
from app.db.models import Event, Provider
from app.db.seed_helpers import derive_provider_slug
from app.schemas.event import EventCreate
from app.v1.serializers import business_from_provider, event_from_row

router = APIRouter(prefix="/api/admin", tags=["v1-admin-crud"])

DbSession = Annotated[Session, Depends(get_db)]


AdminAuth = Annotated[None, Depends(require_admin)]


class BusinessWrite(BaseModel):
    name: str = Field(min_length=1)
    category: str = "services"
    phone: str | None = None
    address: str | None = None
    website: str | None = None
    description: str | None = None
    status: str | None = None


class BusinessPatch(BaseModel):
    name: str | None = None
    category: str | None = None
    phone: str | None = None
    address: str | None = None
    website: str | None = None
    description: str | None = None
    status: str | None = None
    is_active: bool | None = None


class EventWrite(BaseModel):
    title: str
    date: date_type
    start_time: str = "09:00"
    end_time: str | None = None
    location_name: str
    description: str = ""
    event_url: str = ""
    status: str = "live"


class EventPatch(BaseModel):
    title: str | None = None
    date: date_type | None = None
    start_time: str | None = None
    end_time: str | None = None
    location_name: str | None = None
    description: str | None = None
    event_url: str | None = None
    status: str | None = None


def _parse_time(s: str) -> time:
    raw = s.strip()
    if len(raw) == 5:
        return time.fromisoformat(raw + ":00")
    return time.fromisoformat(raw)


@router.get("/businesses")
def admin_list_businesses(
    _: AdminAuth,
    db: DbSession,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = None,
) -> dict:
    stmt = select(Provider).where(Provider.draft.is_(False))
    if q and q.strip():
        stmt = stmt.where(Provider.provider_name.ilike(f"%{q.strip()}%"))
    rows = list(db.scalars(stmt).offset(offset).limit(limit).all())
    total = len(list(db.scalars(stmt).all()))
    return {
        "items": [business_from_provider(p) for p in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/businesses", status_code=201)
def admin_create_business(_: AdminAuth, db: DbSession, body: BusinessWrite) -> dict:
    name = body.name.strip()
    provider = Provider(
        provider_name=name,
        category=body.category.strip(),
        phone=body.phone,
        address=body.address,
        website=body.website,
        description=body.description,
        slug=derive_provider_slug(db, name),
        draft=False,
        is_active=True,
        verified=True,
        pending_review=False,
        source="manual",
    )
    db.add(provider)
    create_provider_and_entity(db, provider)
    db.commit()
    db.refresh(provider)
    return business_from_provider(provider)


@router.patch("/businesses/{provider_id}")
def admin_patch_business(
    _: AdminAuth,
    db: DbSession,
    provider_id: str,
    body: BusinessPatch,
) -> dict:
    p = db.get(Provider, provider_id)
    if p is None:
        raise HTTPException(status_code=404, detail="not_found")
    if body.name is not None:
        p.provider_name = body.name.strip()
    if body.category is not None:
        p.category = body.category.strip()
    if body.phone is not None:
        p.phone = body.phone
    if body.address is not None:
        p.address = body.address
    if body.website is not None:
        p.website = body.website
    if body.description is not None:
        p.description = body.description
    if body.is_active is not None:
        p.is_active = body.is_active
    if body.status == "hidden":
        p.is_active = False
    elif body.status == "published":
        p.is_active = True
        p.draft = False
    db.commit()
    db.refresh(p)
    return business_from_provider(p)


@router.delete("/businesses/{provider_id}")
def admin_delete_business(_: AdminAuth, db: DbSession, provider_id: str) -> dict:
    p = db.get(Provider, provider_id)
    if p is None:
        raise HTTPException(status_code=404, detail="not_found")
    p.is_active = False
    p.draft = True
    db.commit()
    return {"ok": True, "id": provider_id, "status": "hidden"}


@router.get("/events")
def admin_list_events(
    _: AdminAuth,
    db: DbSession,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = None,
) -> dict:
    stmt = select(Event)
    if status:
        stmt = stmt.where(Event.status == status)
    count_stmt = select(func.count()).select_from(Event)
    if status:
        count_stmt = count_stmt.where(Event.status == status)
    total = int(db.scalar(count_stmt) or 0)
    rows = list(
        db.scalars(stmt.order_by(Event.date.desc()).offset(offset).limit(limit)).all()
    )
    return {
        "items": [event_from_row(e) for e in rows],
        "total": len(rows),
        "limit": limit,
        "offset": offset,
    }


@router.post("/events", status_code=201)
def admin_create_event(_: AdminAuth, db: DbSession, body: EventWrite) -> dict:
    payload = EventCreate(
        title=body.title.strip(),
        date=body.date,
        start_time=_parse_time(body.start_time),
        end_time=_parse_time(body.end_time) if body.end_time else None,
        location_name=body.location_name.strip(),
        description=body.description or body.title,
        event_url=body.event_url or "https://havasu-chat.example.com",
        status=body.status,
        source="manual",
        created_by="admin",
        verified=True,
    )
    event = Event.from_create(payload)
    db.add(event)
    create_event_and_entity(db, event)
    db.commit()
    db.refresh(event)
    return event_from_row(event)


@router.patch("/events/{event_id}")
def admin_patch_event(
    _: AdminAuth,
    db: DbSession,
    event_id: str,
    body: EventPatch,
) -> dict:
    ev = db.get(Event, event_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="not_found")
    if body.title is not None:
        ev.title = body.title.strip()
        ev.normalized_title = ev.title.lower()
    if body.date is not None:
        ev.date = body.date
    if body.start_time is not None:
        ev.start_time = _parse_time(body.start_time)
    if body.end_time is not None:
        ev.end_time = _parse_time(body.end_time)
    if body.location_name is not None:
        ev.location_name = body.location_name.strip()
        ev.location_normalized = ev.location_name.lower()
    if body.description is not None:
        ev.description = body.description
    if body.event_url is not None:
        ev.event_url = body.event_url
    if body.status is not None:
        ev.status = body.status
    db.commit()
    db.refresh(ev)
    return event_from_row(ev)


@router.delete("/events/{event_id}")
def admin_delete_event(_: AdminAuth, db: DbSession, event_id: str) -> dict:
    ev = db.get(Event, event_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="not_found")
    ev.status = "hidden"
    db.commit()
    return {"ok": True, "id": event_id, "status": "hidden"}
