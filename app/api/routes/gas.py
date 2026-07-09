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
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.conditions.cache import read_source
from app.conditions.constants import SOURCE_GAS
from app.core.rate_limit import limiter, public_api_rate_limit, public_html_rate_limit
from app.core.templates import make_templates
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import get_db
from app.gas.service import GasBoard, board_from_cache, to_legacy_station_dict

router = APIRouter(tags=["gas"])

# make_templates() runs the shared registrars. This page learned why that
# matters the hard way: without the ``canonical_url``/``absolute_url`` globals,
# desert_base silently skips its whole canonical + Open Graph head block — live
# /gas once shipped with NO canonical and NO og:* tags after skipping the calls.
templates = make_templates()

# Number of cheapest stations to surface above the full table. The prototype's
# cut-off "top 5" is replaced with a clean 6-up grid (UI build guide §4.11).
_CHEAPEST_SHOWN = 6


def _read_board(
    db: Session,
) -> tuple[GasBoard, dict[str, Any], str | None, str | None]:
    """Return (board, city_avg, fetched_at_label, fetched_at_time_label).

    The board is the single source of truth (v4.4 PR-1) the strip tile and home
    panel also use, so /gas can never disagree with them on a station or a
    cheapest figure. ``city_avg`` is the page-level "typical price" per grade — the
    MEDIAN across the exact board stations shown, not the pull's stored mean (a
    simple mean let the high-price outliers skew it above the pump most drivers
    see; 2026-07-08 re-audit: mean $3.83 vs median $3.72). Computed off the board
    so it can never disagree with the displayed table. Both human timestamps
    derive from ``board.pulled_at`` — one clock.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    row = read_source(db, SOURCE_GAS, now=now)
    board = board_from_cache(row, now=now)
    _short_to_long = {"reg": "regular", "mid": "midgrade", "prem": "premium", "dsl": "diesel"}
    city_avg: dict[str, Any] = {
        lng: m
        for sh, lng in _short_to_long.items()
        if (m := board.median_price(sh)) is not None
    }
    label = _format_fetched_at(board.pulled_at) if board.pulled_at else None
    time_label = _format_fetched_at_time(board.pulled_at) if board.pulled_at else None
    return board, city_avg, label, time_label


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
    """v4 shell context (v4.5 PR-2): the cond-tile strip for base_redesign. On /gas
    the gas cond-tile is a plain span (``cond_gas_plain`` — no caret/panel, you're
    already on the gas page). Imported lazily to avoid a module-load cycle.
    """
    from app.core.timezone import now_lake_havasu
    from app.home import redesign

    now = now_lake_havasu()
    return {
        "cond_tiles": redesign.conditions_tiles(db, now=now),
        "today_label": now.strftime("%A, %B ") + str(now.day),
        "cond_gas_plain": True,
        "active_tab": "gas",
    }


@router.get("/gas", response_class=HTMLResponse)
@limiter.limit(public_html_rate_limit)
def gas_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    board, city_avg, fetched_at_label, fetched_at_time_label = _read_board(db)
    # M12 (2026-07-08 re-audit): the price-sorted table is the only cheapest view
    # now (the "Cheapest today" card was removed), so sort it regular-cheapest-first
    # by construction rather than relying on the pull's stored order. Stations
    # without a regular price sink to the bottom (they still show under their grade).
    ranked = sorted(
        board.stations,
        key=lambda s: (s.prices.get("reg") is None, s.prices.get("reg") or 0.0),
    )
    stations = [to_legacy_station_dict(s) for s in ranked]
    long_labels = {"regular": "Regular", "midgrade": "Midgrade", "premium": "Premium", "diesel": "Diesel"}
    short_to_long = {"reg": "regular", "mid": "midgrade", "prem": "premium", "dsl": "diesel"}
    # v4.4 PR-6: the grade segment offers only the grades the data actually has
    # (a single grade -> no segment). The table columns stay the four canonical
    # grades so the tabular view still shows what each station carries.
    grades_available = [short_to_long[g] for g in board.grades_available if g in short_to_long]
    return templates.TemplateResponse(
        request=request,
        name="gas_prices_lake.html",
        context={
            **_shell_context(db),
            "data": {"station_count": len(stations)},
            "staleness_label": board.label,
            "is_stale": board.is_stale,
            "fetched_at_label": fetched_at_label,
            "fetched_at_time_label": fetched_at_time_label,
            "has_data": bool(stations),
            "stations": stations,
            "city_avg": city_avg,
            "grades": ["regular", "midgrade", "premium", "diesel"],
            "grades_available": grades_available,
            "single_grade": len(grades_available) <= 1,
            "grade_labels": {
                "regular": "Regular",
                "midgrade": "Mid",
                "premium": "Premium",
                "diesel": "Diesel",
            },
            "grade_seg_labels": long_labels,
        },
    )


@router.get("/api/gas", response_class=JSONResponse)
@limiter.limit(public_api_rate_limit)
def gas_api(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    board, city_avg, _, _ = _read_board(db)
    stations = [to_legacy_station_dict(s) for s in board.stations]
    pulled_iso = (
        board.pulled_at.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")
        if board.pulled_at
        else None
    )
    return JSONResponse(
        content={
            "stations": stations,
            "cheapest": [to_legacy_station_dict(s) for s in board.cheapest("reg", _CHEAPEST_SHOWN)],
            "city_avg": city_avg,
            "station_count": len(stations),
            "grades_available": board.grades_available,
            "updated_at_iso": pulled_iso,
            "staleness_label": board.label,
            "is_stale": board.is_stale,
        }
    )
