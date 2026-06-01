"""PATCH /api/admin/contributions/{id} — approve / reject / needs_info (spec §4.4)."""

from __future__ import annotations

from datetime import date, time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.routes.admin_contributions import require_admin
from app.contrib.approval_service import (
    approve_contribution_as_event,
    approve_contribution_as_program,
    approve_contribution_as_provider,
)
from app.core.timezone import now_lake_havasu
from app.db.contribution_store import get_contribution, update_contribution_status
from app.db.database import get_db
from app.schemas.contribution import (
    ContributionResponse,
    EventApprovalFields,
    ProgramApprovalFields,
    ProviderApprovalFields,
)

router = APIRouter(prefix="/api/admin", tags=["v1-admin-contrib"])

DbSession = Annotated[Session, Depends(get_db)]
AdminAuth = Annotated[None, Depends(require_admin)]


class ContributionAdminPatch(BaseModel):
    action: Literal["approve", "reject", "needs_info"]
    category: str | None = None
    review_notes: str | None = None
    rejection_reason: str | None = None
    fields: dict | None = None


@router.patch("/contributions/{contribution_id}")
def patch_contribution(
    _: AdminAuth,
    db: DbSession,
    contribution_id: int,
    body: ContributionAdminPatch,
) -> ContributionResponse:
    row = get_contribution(db, contribution_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not_found")
    if row.status != "pending":
        raise HTTPException(status_code=400, detail="not_pending")

    if body.action == "needs_info":
        updated = update_contribution_status(
            db, contribution_id, "needs_info", review_notes=body.review_notes
        )
        return ContributionResponse.model_validate(updated)

    if body.action == "reject":
        reason = body.rejection_reason or "other"
        if reason not in (
            "duplicate",
            "out_of_area",
            "spam",
            "incomplete",
            "unverifiable",
            "other",
        ):
            reason = "other"
        updated = update_contribution_status(
            db,
            contribution_id,
            "rejected",
            review_notes=body.review_notes,
            rejection_reason=reason,  # type: ignore[arg-type]
        )
        return ContributionResponse.model_validate(updated)

    extra = body.fields or {}
    cat = (body.category or row.submission_category_hint or "services").strip()
    try:
        if row.entity_type == "provider":
            pf = ProviderApprovalFields(
                name=extra.get("name") or row.submission_name,
                address=extra.get("address"),
                phone=extra.get("phone"),
                hours=extra.get("hours"),
                description=extra.get("description") or row.submission_notes,
                website=extra.get("website") or (
                    str(row.submission_url) if row.submission_url else None
                ),
            )
            approve_contribution_as_provider(db, contribution_id, pf, cat)
        elif row.entity_type == "program":
            desc = (
                extra.get("description")
                or row.submission_notes
                or row.submission_name
                or "Program submitted via Ask Hava."
            )
            if len(desc) < 20:
                desc = desc + " — Lake Havasu City program listing."
            pr = ProgramApprovalFields(
                title=extra.get("title") or row.submission_name,
                description=desc,
                schedule_start_time=extra.get("schedule_start_time") or "09:00",
                schedule_end_time=extra.get("schedule_end_time") or "17:00",
                location_name=extra.get("location_name") or "Lake Havasu City",
                provider_name=extra.get("provider_name") or row.submission_name,
            )
            approve_contribution_as_program(db, contribution_id, pr, cat)
        elif row.entity_type == "event":
            today = now_lake_havasu().date()
            ev_date = row.event_date or today
            st = row.event_time_start or time(9, 0)
            ev_desc = (
                extra.get("description")
                or row.submission_notes
                or row.submission_name
                or "Event submitted via Ask Hava."
            )
            if len(ev_desc) < 20:
                ev_desc = ev_desc + " — Lake Havasu City event listing."
            evf = EventApprovalFields(
                title=extra.get("title") or row.submission_name,
                description=ev_desc,
                date=extra.get("date") if isinstance(extra.get("date"), date) else ev_date,
                start_time=st,
                end_time=row.event_time_end,
                location_name=extra.get("location_name") or "Lake Havasu City",
                event_url=extra.get("event_url")
                or (str(row.submission_url) if row.submission_url else "https://havasu-chat.example.com"),
                source_url=row.source_url,
            )
            approve_contribution_as_event(db, contribution_id, evf, [])
        else:
            update_contribution_status(
                db, contribution_id, "approved", review_notes=body.review_notes
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = get_contribution(db, contribution_id)
    return ContributionResponse.model_validate(row)
