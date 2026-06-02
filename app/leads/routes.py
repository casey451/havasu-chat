"""Dormant lead-capture HTTP hook — Phase B7 (flag-gated).

A single POST endpoint that is DORMANT by default: when ``LEADS_ENABLED`` is
off (the default) it returns 404, identical to a route that does not exist, so
the dormant feature leaks no surface. When the flag is on it records exactly
one :class:`app.db.models.Lead` via :func:`app.leads.capture.capture_lead` and
returns its id.

NO billing/payment/pricing — this is plumbing only. There is no UI surfacing of
leads beyond this minimal capture endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session as SqlSession

from app.db.database import get_db
from app.db.models import Provider
from app.leads.capture import LeadInput, capture_lead, leads_enabled

router = APIRouter(tags=["leads"])


class LeadCaptureBody(BaseModel):
    provider_id: str
    category: str | None = None
    source: str = "web_form"
    intent_key: str | None = None
    chat_log_id: str | None = None
    query_log_id: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    contact_message: str | None = None


@router.post("/api/leads")
def api_capture_lead(
    request: Request,
    body: LeadCaptureBody,
    db: SqlSession = Depends(get_db),
) -> JSONResponse:
    # Dormant: behave as if the route does not exist when the flag is off.
    if not leads_enabled():
        return JSONResponse(status_code=404, content={"detail": "not_found"})
    provider = db.get(Provider, body.provider_id)
    if provider is None:
        return JSONResponse(status_code=404, content={"detail": "provider_not_found"})
    row = capture_lead(
        db,
        LeadInput(
            provider_id=body.provider_id,
            category=body.category,
            source=body.source,
            intent_key=body.intent_key,
            chat_log_id=body.chat_log_id,
            query_log_id=body.query_log_id,
            contact_name=body.contact_name,
            contact_phone=body.contact_phone,
            contact_email=body.contact_email,
            contact_message=body.contact_message,
        ),
    )
    db.commit()
    return JSONResponse(status_code=201, content={"lead_id": row.id if row else None})
