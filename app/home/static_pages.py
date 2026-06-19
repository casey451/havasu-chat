"""Static trust pages -- ``/about``, ``/help``, ``/contact`` (WP-1, DL-18).

Three server-rendered Lake Light pages that extend ``lake_light_base.html``.
They take no DB and no dynamic context, so they render fast and never 500 on a
cold database. Registered in ``app/main.py`` via ``include_router`` (see the
``include_router`` block alongside ``home_router``).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.provider_name import register_template_filters, register_template_globals

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)

router = APIRouter(tags=["static-pages"])


def _t(request: Request, name: str) -> str:
    """Serve the Lake variant when the THEME flag resolves to lake (Phase 5a);
    default stays desert until the Phase-8 flip — see app/core/theme.py."""
    if getattr(request.state, "theme", "desert") == "lake":
        return f"{name[:-5]}_lake.html"
    return name


@router.get("/about", response_class=HTMLResponse)
def about_page(request: Request) -> HTMLResponse:
    """Static About page."""
    return templates.TemplateResponse(request=request, name=_t(request, "about.html"), context={})


@router.get("/help", response_class=HTMLResponse)
def help_page(request: Request) -> HTMLResponse:
    """Static Help / FAQ page."""
    return templates.TemplateResponse(request=request, name=_t(request, "help.html"), context={})


@router.get("/contact", response_class=HTMLResponse)
def contact_page(request: Request) -> HTMLResponse:
    """Static Contact page."""
    return templates.TemplateResponse(
        request=request, name=_t(request, "contact.html"), context={}
    )
