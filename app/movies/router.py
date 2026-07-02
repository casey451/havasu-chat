"""Hava -- ``GET /movies`` route: showtimes at Lake Havasu City theaters.

Self-contained like the other page routers (own Jinja env + template globals).
Showtimes come from the dedicated ``movie_showtimes`` table
(app/movies/store.py, populated by scripts/scrape_movies_havasu.py on a cron).
(This docstring previously said Event rows tagged ``movie`` — audit doc-rot
fix 2026-07-02.)
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.provider_name import register_template_filters, register_template_globals
from app.core.timezone import now_lake_havasu
from app.db.database import get_db
from app.movies import posters
from app.movies.queries import has_free_kids, showtimes_for_day

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)

router = APIRouter(tags=["movies"])

# How many days of showtimes to offer in the date picker (the feed only carries
# ~1-2 weeks anyway). Days with nothing render an honest empty state.
_DATE_SPAN = 7


def _parse_selected(raw: str | None, today: date) -> date:
    """Clamp a ``?date=`` param to the visible window; default to today."""
    if raw:
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            return today
        if today <= d <= today + timedelta(days=_DATE_SPAN - 1):
            return d
    return today


def _date_chips(today: date, selected: date) -> list[dict]:
    chips: list[dict] = []
    for i in range(_DATE_SPAN):
        d = today + timedelta(days=i)
        chips.append(
            {
                "iso": d.isoformat(),
                "dow": "Today" if d == today else d.strftime("%a"),
                "day": str(d.day),
                "on": d == selected,
            }
        )
    return chips


@router.get("/img/poster", response_model=None)
def poster_proxy(u: str) -> Response:
    """Re-serve a theater poster from our own origin (see :mod:`app.movies.posters`).

    The ``u`` param is the upstream poster URL; only the Veezi poster host is
    allowed (anything else 400s), so this can't be turned into an open proxy.
    A long ``Cache-Control`` lets the browser/CDN keep the bytes after the first
    hit — the upstream is only touched on a cold cache.
    """
    try:
        data, ctype = posters.fetch_poster(u)
    except posters.PosterNotAllowed as exc:
        raise HTTPException(status_code=400, detail="poster host not allowed") from exc
    except posters.PosterFetchError as exc:
        raise HTTPException(status_code=502, detail="poster fetch failed") from exc
    return Response(
        content=data,
        media_type=ctype,
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("/movies", response_class=HTMLResponse, response_model=None)
def serve_movies(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    now = now_lake_havasu()
    today = now.date()
    selected = _parse_selected(request.query_params.get("date"), today)
    day_label = selected.strftime("%A, %B ") + str(selected.day)
    is_today = selected == today
    # THEME flag (Lake Ink & Brass): the lake skin renders the SAME context
    # through base_lake; default stays desert until/unless the flip.
    movies_template = "movies_lake.html"
    return templates.TemplateResponse(
        request=request,
        name=movies_template,
        context={
            "today_label": now.strftime("%A, %B ") + str(now.day),
            "now_label": now.strftime("%I:%M %p").lstrip("0"),
            "day_label": day_label,
            "is_today": is_today,
            "date_chips": _date_chips(today, selected),
            "theaters": showtimes_for_day(db, day=selected, now=now),
            "free_kids": has_free_kids(db, day=selected),
            "active_tab": "movies",
        },
    )
