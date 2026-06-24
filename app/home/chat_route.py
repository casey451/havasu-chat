"""Hava — ``GET /chat`` route (BUILD.md step 5).

The new chat surface where the home composer's submission lands. Renders
the chat thread as a scaffold; ``/static/js/chat-new.js`` drives the actual
turn-by-turn rendering and POSTs to the existing ``/api/chat`` endpoint.

Initial query from ``/chat?q=…`` is read by the JS from ``location.search``
on page load, so the same URL is shareable and the back-button works.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.categories import leaf_query
from app.core.provider_name import register_template_filters, register_template_globals
from app.db.database import get_db
from app.home.calendar_view import is_discovery_query

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
        # Service/business → its directory leaf. Applies in BOTH themes (existing
        # conservative B.3 behaviour): "plumbers", "boat rentals" → category page.
        leaf = leaf_query.match_leaf_query(db, cleaned)
        # Need-shaped service asks the exact matcher misses ("hvac needs repair",
        # "pool service repair") still route to their leaf when one unambiguous
        # category keyword carries the query — else fall through unchanged.
        if leaf is None:
            leaf = leaf_query.match_leaf_service_intent(db, cleaned)
        if leaf is not None:
            return RedirectResponse(
                url=f"/categories/{leaf.department_slug}/{leaf.slug}",
                status_code=302,
            )
        # The concierge is an intent ROUTER — it routes, it doesn't chat (Lake is
        # the only theme since the desert lineage was deleted 2026-06-24).
        # Discovery ("what's happening tonight") → the /calendar surface; anything
        # else we couldn't place → a graceful search, never Tier-3 prose.
        if is_discovery_query(cleaned):
            return RedirectResponse(url=f"/calendar?q={quote(cleaned)}", status_code=302)
        return RedirectResponse(url=f"/search?q={quote(cleaned)}", status_code=302)
    # Empty query (the "Ask" front door): the lake chat scaffold.
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={"initial_query": cleaned or None},
    )
