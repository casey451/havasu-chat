"""Hava — ``GET /chat`` route (BUILD.md step 5).

The new chat surface where the home composer's submission lands. Renders
the chat thread as a scaffold; ``/static/js/chat-new.js`` drives the actual
turn-by-turn rendering and POSTs to the existing ``/api/chat`` endpoint.

Initial query from ``/chat?q=…`` is read by the JS from ``location.search``
on page load, so the same URL is shareable and the back-button works.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(tags=["chat-ui"])


@router.get("/chat", response_class=HTMLResponse)
def serve_chat(request: Request, q: str | None = None) -> HTMLResponse:
    """Render the /chat scaffold. JS reads ?q=… and fires the first turn."""
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={"initial_query": (q or "").strip() or None},
    )
