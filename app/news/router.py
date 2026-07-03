"""``GET /news`` — the local news page (v4 shell).

Reads the aggregated headline cache (:mod:`app.news.store`) and links every
headline out to its original source. No article bodies are rendered (paywall/
copyright rule 6). Honest-omit: an empty cache shows a friendly empty state.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.templates import make_templates
from app.core.timezone import now_lake_havasu
from app.db.database import get_db
from app.home import redesign
from app.news import store

router = APIRouter(tags=["news"])

templates = make_templates()


@router.get("/news", response_class=HTMLResponse)
def serve_news(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    now = now_lake_havasu()
    view = store.page_view(db, now=now)
    return templates.TemplateResponse(
        request=request,
        name="news_redesign.html",
        context={
            "news": view,
            "today_label": now.strftime("%A, %B ") + str(now.day),
            "cond_tiles": redesign.conditions_tiles(db, now=now),
            "gas": redesign.gas_top5(db, now=now),
            "active_tab": "news",
        },
    )
