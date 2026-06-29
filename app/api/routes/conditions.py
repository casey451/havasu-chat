"""GET /api/conditions — live conditions JSON (Phase 8a)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.conditions.api_payload import build_conditions_api_payload
from app.core.rate_limit import limiter, public_api_rate_limit
from app.db.database import get_db

router = APIRouter(prefix="/api", tags=["conditions"])


@router.get("/conditions")
@limiter.limit(public_api_rate_limit)
def get_conditions(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    payload = build_conditions_api_payload(db)
    return JSONResponse(content=payload)
