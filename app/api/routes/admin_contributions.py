"""Admin JSON API for contribution queue (Phase 5.1 + 5.2 enrichment)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.admin.auth import COOKIE_NAME, verify_admin_cookie
from app.contrib.enrichment import enrich_contribution
from app.db.contribution_store import (
    create_contribution,
    get_contribution,
    list_contributions,
    update_contribution_status,
)
from app.db.database import SessionLocal, get_db
from app.schemas.contribution import (
    ContributionCreate,
    ContributionResponse,
    ContributionStatusUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin-contributions"])


def require_admin(request: Request) -> None:
    """Same session cookie as HTML admin (``POST /admin/login``)."""
    if not verify_admin_cookie(request.cookies.get(COOKIE_NAME)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required",
        )


AdminAuth = Annotated[None, Depends(require_admin)]
DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/contributions",
    response_model=ContributionResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_contribution(
    _: AdminAuth,
    background_tasks: BackgroundTasks,
    db: DbSession,
    body: ContributionCreate,
) -> ContributionResponse:
    row = create_contribution(db, body, submitter_ip_hash=None)
    background_tasks.add_task(enrich_contribution, row.id, SessionLocal)
    return ContributionResponse.model_validate(row)


@router.get("/contributions", response_model=list[ContributionResponse])
def get_contributions(
    _: AdminAuth,
    db: DbSession,
    status_filter: str | None = Query(None, alias="status"),
    entity_type: str | None = None,
    source: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[ContributionResponse]:
    rows = list_contributions(
        db,
        status=status_filter,
        entity_type=entity_type,
        source=source,
        limit=limit,
        offset=offset,
    )
    return [ContributionResponse.model_validate(r) for r in rows]


@router.get("/contributions/{contribution_id}", response_model=ContributionResponse)
def get_contribution_by_id(
    _: AdminAuth,
    db: DbSession,
    contribution_id: int,
) -> ContributionResponse:
    row = get_contribution(db, contribution_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return ContributionResponse.model_validate(row)


@router.patch(
    "/contributions/{contribution_id}/status",
    response_model=ContributionResponse,
)
def patch_contribution_status(
    _: AdminAuth,
    db: DbSession,
    contribution_id: int,
    body: ContributionStatusUpdate,
) -> ContributionResponse:
    try:
        row = update_contribution_status(
            db,
            contribution_id,
            body.status,
            review_notes=body.review_notes,
            rejection_reason=body.rejection_reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return ContributionResponse.model_validate(row)


@router.post(
    "/contributions/{contribution_id}/enrich",
    status_code=status.HTTP_202_ACCEPTED,
)
def post_enrich_contribution(
    _: AdminAuth,
    background_tasks: BackgroundTasks,
    db: DbSession,
    contribution_id: int,
) -> JSONResponse:
    row = get_contribution(db, contribution_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    background_tasks.add_task(enrich_contribution, contribution_id, SessionLocal)
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"contribution_id": contribution_id, "enrichment": "scheduled"},
    )
