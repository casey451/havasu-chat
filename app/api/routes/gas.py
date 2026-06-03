"""GET /gas -- per-station Lake Havasu City gas prices page (2026-05-29).

Reads the daily payload written by scripts/gas_prices_pull.py from
external_conditions_cache (SOURCE_GAS) and renders the cheapest few stations
plus the full station list. JSON sibling at /api/gas for the chat layer /
clients.

Sandstone re-skin (2026-06-02, UI build guide §4.11):
- Source column + Google-feed footer line removed.
- Freshness banner derives BOTH its staleness label and its displayed
  timestamp from a SINGLE clock — ``row.fetched_at`` — so the two can never
  contradict each other (the payload's separately-stamped ``updated_at_iso``
  is no longer the thing the banner shows).
- The "cheapest" strip shows 6 stations, not a cut-off "top 5".
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

# Number of cheapest stations to surface above the full table. The prototype's
# cut-off "top 5" is replaced with a clean 6-up grid (UI build guide §4.11).
_CHEAPEST_SHOWN = 6


def _read_payload(db: Session) -> tuple[dict[str, Any], str | None, bool, str | None]:
    """Return (payload, staleness_label, is_stale, fetched_at_label).

    The staleness label AND the human ``fetched_at_label`` are both derived
    from ``row.fetched_at`` — a single source — so the freshness banner can
    never claim "updated 2 min ago" next to a timestamp that says otherwise.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    row = read_source(db, SOURCE_GAS, now=now)
    if row is None or not isinstance(row.data, dict):
        return {}, None, False, None
    label, stale = staleness_label(row.fetched_at, now)
    fetched_at_label = _format_fetched_at(row.fetched_at)
    return row.data, label, bool(stale or row.is_stale), fetched_at_label


def _format_fetched_at(fetched_at: datetime) -> str:
    """Human timestamp for the freshness banner (same clock as the label)."""
    return fetched_at.strftime("%b ") + str(fetched_at.day) + fetched_at.strftime(", %Y %H:%M UTC")


@router.get("/gas", response_class=HTMLResponse)
def gas_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    data, staleness, is_stale, fetched_at_label = _read_payload(db)
    stations = [s for s in (data.get("stations") or []) if isinstance(s, dict)]
    cheapest = [s for s in (data.get("cheapest") or []) if isinstance(s, dict)]
    return templates.TemplateResponse(
        request=request,
        name="gas_prices.html",
        context={
            "data": data,
            "staleness_label": staleness,
            "is_stale": is_stale,
            "fetched_at_label": fetched_at_label,
            "has_data": bool(stations),
            "stations": stations,
            "cheapest": cheapest[:_CHEAPEST_SHOWN],
            "city_avg": data.get("city_avg") or {},
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
    data, staleness, is_stale, _ = _read_payload(db)
    return JSONResponse(content={**data, "staleness_label": staleness, "is_stale": is_stale})
