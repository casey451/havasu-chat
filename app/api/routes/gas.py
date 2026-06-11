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
from app.conditions.constants import GAS_STALE_AFTER_HOURS, SOURCE_GAS
from app.conditions.staleness import staleness_label
from app.core.provider_name import register_template_filters, register_template_globals
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import get_db

router = APIRouter(tags=["gas"])

_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
# Every Jinja2Templates instance must run the shared registrars: without
# ``canonical_url``/``absolute_url`` globals, desert_base silently skips its
# whole canonical + Open Graph head block — live /gas shipped with NO
# canonical and NO og:* tags because this module skipped the calls.
register_template_filters(templates)
register_template_globals(templates)

# Number of cheapest stations to surface above the full table. The prototype's
# cut-off "top 5" is replaced with a clean 6-up grid (UI build guide §4.11).
_CHEAPEST_SHOWN = 6


def _read_payload(
    db: Session,
) -> tuple[dict[str, Any], str | None, bool, str | None, str | None]:
    """Return (payload, staleness_label, is_stale, fetched_at_label, fetched_at_time_label).

    The staleness label AND both human timestamps derive from a SINGLE clock
    (``row.fetched_at``), so the banner can never read "updated 2 min ago" next
    to an absolute time that disagrees. ``fetched_at_time_label`` is a time-only
    form ("2:30 PM") for the "Cheapest today (as of {time})" heading.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    row = read_source(db, SOURCE_GAS, now=now)
    if row is None or not isinstance(row.data, dict):
        return {}, None, False, None, None
    label, stale = staleness_label(row.fetched_at, now, stale_after_hours=GAS_STALE_AFTER_HOURS)
    fetched_at_label = _format_fetched_at(row.fetched_at)
    fetched_at_time_label = _format_fetched_at_time(row.fetched_at)
    return row.data, label, bool(stale or row.is_stale), fetched_at_label, fetched_at_time_label


def _local_fetched_at(fetched_at: datetime) -> datetime:
    """``fetched_at`` (stored as naive UTC) rendered in Lake Havasu local time."""
    return fetched_at.replace(tzinfo=UTC).astimezone(LAKE_HAVASU_TZ)


def _format_fetched_at(fetched_at: datetime) -> str:
    """Human date+time for the page, in Lake Havasu local time (G-1).

    Render as America/Phoenix so the timestamp reads in the visitor's local
    time, not a raw UTC clock.
    """
    local = _local_fetched_at(fetched_at)
    hour12 = local.strftime("%I:%M %p").lstrip("0")
    return local.strftime("%b ") + str(local.day) + local.strftime(", %Y ") + hour12


def _format_fetched_at_time(fetched_at: datetime) -> str:
    """Time-only form ("2:30 PM") in Lake Havasu local time, for the
    "Cheapest today (as of {time})" heading."""
    return _local_fetched_at(fetched_at).strftime("%I:%M %p").lstrip("0")


def _shell_context(db: Session) -> dict[str, Any]:
    """Header nav + conditions ribbon context, so /gas wears the full Sandstone
    shell (the ribbon partial in sandstone_base renders only when
    ``utility_chips`` is supplied). Built from the canonical home builders;
    imported lazily to avoid a module-load cycle with app.home.router.
    """
    from app.home import sandstone
    from app.home.router import _utility_chips

    return {
        "utility_chips": _utility_chips(db),
        "primary_nav": sandstone.primary_nav(),
        "mega_columns": sandstone.mega_columns(db),
    }


@router.get("/gas", response_class=HTMLResponse)
def gas_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    data, staleness, is_stale, fetched_at_label, fetched_at_time_label = _read_payload(db)
    stations = [s for s in (data.get("stations") or []) if isinstance(s, dict)]
    cheapest = [s for s in (data.get("cheapest") or []) if isinstance(s, dict)]
    return templates.TemplateResponse(
        request=request,
        name="gas_prices.html",
        context={
            **_shell_context(db),
            "data": data,
            "staleness_label": staleness,
            "is_stale": is_stale,
            "fetched_at_label": fetched_at_label,
            "fetched_at_time_label": fetched_at_time_label,
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
    data, staleness, is_stale, _, _ = _read_payload(db)
    return JSONResponse(content={**data, "staleness_label": staleness, "is_stale": is_stale})
