"""GET /api/conditions — live conditions JSON (Phase 8a)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.conditions.api_payload import build_conditions_api_payload
from app.db.database import get_db

router = APIRouter(prefix="/api", tags=["conditions"])


@router.get("/conditions")
def get_conditions(db: Session = Depends(get_db)) -> JSONResponse:
    payload = build_conditions_api_payload(db)
    return JSONResponse(content=payload)
