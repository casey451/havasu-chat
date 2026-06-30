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
from app.chat.query_intent import INTENT_AI, classify_query_intent
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
    nf: int | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    """Render the /chat scaffold. JS reads ?q=… and fires the first turn.

    Routing (F13, 2026-06-30): /chat is the AI entry point — a question or
    natural-language ask is answered by the concierge, and anything we can't
    place no longer dead-ends at keyword ``/search`` (it falls through to the AI
    too). The one high-confidence shortcut is kept: a query that maps EXACTLY to
    a single gate-clearing taxonomy leaf ("plumbers", "boat rentals") still 302s
    straight to that category page, and a non-question discovery ask goes to the
    /calendar surface. ``nf=1`` marks an arrival from a zero-result keyword
    search so the scaffold shows a short "no exact matches" note above the AI
    answer.
    """
    cleaned = (q or "").strip()
    if cleaned:
        # Questions / natural language / "open now"-style asks → the AI directly,
        # ahead of the keyword shortcuts ("is there a plumber near me" answers,
        # it does not redirect to the plumbers page).
        if classify_query_intent(cleaned) == INTENT_AI:
            return _scaffold(request, cleaned, fallback=bool(nf))
        # Service/business → its directory leaf ("plumbers", "boat rentals").
        leaf = leaf_query.match_leaf_query(db, cleaned)
        # Need-shaped service asks the exact matcher misses ("hvac needs repair")
        # still route to their leaf when one unambiguous category keyword carries
        # the query — else fall through to the AI.
        if leaf is None:
            leaf = leaf_query.match_leaf_service_intent(db, cleaned)
        if leaf is not None:
            return RedirectResponse(
                url=f"/categories/{leaf.department_slug}/{leaf.slug}",
                status_code=302,
            )
        # Non-question discovery ("events this weekend") → the /calendar surface.
        if is_discovery_query(cleaned):
            return RedirectResponse(url=f"/calendar?q={quote(cleaned)}", status_code=302)
        # Anything else (descriptive asks, "swimming and splash pads", a business
        # name we couldn't place) → the AI, never a keyword dead-end.
        return _scaffold(request, cleaned, fallback=bool(nf))
    # Empty query (the "Ask" front door): the lake chat scaffold.
    return _scaffold(request, None, fallback=False)


def _scaffold(request: Request, initial_query: str | None, *, fallback: bool) -> HTMLResponse:
    """Render the chat scaffold; chat-new.js reads ?q from the URL and fires the
    first AI turn. ``fallback`` shows the zero-result keyword-search note."""
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={"initial_query": initial_query, "fallback_notice": fallback},
    )
