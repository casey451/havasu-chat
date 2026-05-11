"""Provider profile page route (directory pivot V1).

Renders ``/provider/{slug}`` via Jinja. Source of truth for copy/layout
is ``outputs/chatgpt_response_provider_profile_ux_spec.md``. All sponsor
labeling routes through ``app.chat.disclosure_render.DISCLOSURE_WORD``
so a single string change there propagates here.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.chat.disclosure_render import DISCLOSURE_WORD
from app.db.database import get_db
from app.providers import queries, view_models

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(tags=["providers"])


@router.get("/provider/{slug}", response_class=HTMLResponse)
def serve_provider_profile(
    slug: str, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    provider = queries.get_provider_by_slug(db, slug)
    # 404 covers both missing rows and soft-hidden ones (is_active=False,
    # draft=True). End-users see the standard 404 surface; merchant
    # onboarding is a separate flow.
    if provider is None or not provider.is_active or provider.draft:
        raise HTTPException(status_code=404, detail="Provider not found")

    vm = view_models.build(provider, db=db, viewer_is_owner=False)
    return templates.TemplateResponse(
        request=request,
        name="provider_profile.html",
        context={"vm": vm, "disclosure_word": DISCLOSURE_WORD},
    )
