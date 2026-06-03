"""Business portal routes (Phase 2 §5b).

Public front door for business owners: the advertising catalog (with live
scarcity) and the claim entry point. Payments are intentionally NOT wired yet —
the catalog's CTAs route to enquiry/claim; Stripe checkout is a later increment
once the owner picks a processor + configures keys.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.provider_name import register_template_filters, register_template_globals
from app.db.database import get_db
from app.portal import products

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)

router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def portal_home(request: Request) -> HTMLResponse:
    """Portal landing — claim or advertise."""
    return templates.TemplateResponse(request=request, name="portal_index.html", context={})


@router.get("/advertise", response_class=HTMLResponse)
def portal_advertise(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """The ad catalog with live scarcity. No payments yet — CTAs enquire/claim."""
    return templates.TemplateResponse(
        request=request,
        name="portal_advertise.html",
        context={"catalog": products.catalog(db)},
    )


@router.get("/claim", response_class=HTMLResponse)
def portal_claim(request: Request) -> HTMLResponse:
    """Claim entry point: find your listing (then claim it from its page) or add
    a new one. The per-listing claim itself lives at /claim/{slug} via the
    provider profile's 'Claim this listing' CTA."""
    return templates.TemplateResponse(request=request, name="portal_claim.html", context={})
