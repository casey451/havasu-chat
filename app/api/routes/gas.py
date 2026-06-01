"""GET /gas -- per-station Lake Havasu City gas prices page (2026-05-29).

Reads the daily payload written by scripts/gas_prices_pull.py from
external_conditions_cache (SOURCE_GAS) and renders the top-5 cheapest plus
the full station list. JSON sibling at /api/gas for the chat layer / clients.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.conditions.cache import read_source
from app.conditions.constants import SOURCE_GAS
from app.conditions.staleness import staleness_label
from app.db.database import get_db

router = APIRouter(tags=["gas"])

_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _read_payload(db: Session) -> tuple[dict[str, Any], str | None, bool]:
    now = datetime.now(UTC).replace(tzinfo=None)
    row = read_source(db, SOURCE_GAS, now=now)
    if row is None or not isinstance(row.data, dict):
        return {}, None, False
    label, stale = staleness_label(row.fetched_at, now)
    return row.data, label, bool(stale or row.is_stale)


@router.get("/gas", response_class=HTMLResponse)
def gas_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    data, staleness, is_stale = _read_payload(db)
    return templates.TemplateResponse(
        request=request,
        name="gas_prices.html",
        context={
            "data": data,
            "staleness_label": staleness,
            "is_stale": is_stale,
            "has_data": bool(data.get("stations")),
            "grades": ["regular", "midgrade", "premium", "diesel"],
            "grade_labels": {
                "regular": "Regular",
                "midgrade": "Mid",
                "premium": "Premium",
                "diesel": "Diesel",
            },
        },
    )


@router.get("/api/gas", response_class=JSONResponse)
def gas_api(db: Session = Depends(get_db)) -> JSONResponse:
    data, staleness, is_stale = _read_payload(db)
    return JSONResponse(
        content={**data, "staleness_label": staleness, "is_stale": is_stale}
    )
