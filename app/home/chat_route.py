"""Hava — ``GET /chat`` route (BUILD.md step 5).

The new chat surface where the home composer's submission lands. Renders
the chat thread as a scaffold; ``/static/js/chat-new.js`` drives the actual
turn-by-turn rendering and POSTs to the existing ``/api/chat`` endpoint.

Initial query from ``/chat?q=…`` is read by the JS from ``location.search``
on page load, so the same URL is shareable and the back-button works.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.categories import leaf_query
from app.core.provider_name import register_template_filters, register_template_globals
from app.db.database import get_db

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)

router = APIRouter(tags=["chat-ui"])


@router.get("/chat", response_class=HTMLResponse, response_model=None)
def serve_chat(
    request: Request,
    q: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    """Render the /chat scaffold. JS reads ?q=… and fires the first turn.

    B.3 chat routing: when the query maps EXACTLY to a single gate-clearing
    taxonomy leaf ("plumbers", "boat rentals", "med spas"), 302 straight to that
    leaf page instead of opening a conversational turn. Descriptive/ambiguous
    queries fall through to chat unchanged (Casey's confirmed conservative
    threshold).
    """
    cleaned = (q or "").strip()
    if cleaned:
        leaf = leaf_query.match_leaf_query(db, cleaned)
        if leaf is not None:
            return RedirectResponse(
                url=f"/categories/{leaf.department_slug}/{leaf.slug}",
                status_code=302,
            )
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={"initial_query": cleaned or None},
    )
