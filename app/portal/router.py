"""Business portal routes (Phase 2 §5b).

Public front door for business owners: the advertising catalog (with live
scarcity) and the claim entry point. Payments are intentionally NOT wired yet —
the catalog's CTAs route to enquiry/claim; Stripe checkout is a later increment
once the owner picks a processor + configures keys.
"""

from __future__ import annotations

import html
import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.provider_name import register_template_filters, register_template_globals
from app.db.database import get_db
from app.db.models import AdReservation, AdReservationStatus
from app.home.queries import CATEGORY_LABELS
from app.portal import products

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)

router = APIRouter(prefix="/portal", tags=["portal"])

# Loose email presence check — a server-side guard against blank/obviously
# malformed input, not full RFC validation (the operator confirms by hand).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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


# ── reserve an ad placement (manual-invoice; NO payment processing) ───────────


def _category_options() -> list[tuple[str, str]]:
    """(slug, label) pairs for the category-sponsorship dropdown, label-sorted."""
    return sorted(CATEGORY_LABELS.items(), key=lambda kv: kv[1])


def _notify_operator_of_reservation(reservation_id: str) -> None:
    """Best-effort operator email for a new ad reservation.

    Loads the reservation fresh in its own session and sends an alert email via
    the existing Resend path (``send_alert_email``, which no-ops to a log line
    in AUTH_DEV_MODE). Any failure is swallowed and logged — the reservation is
    already committed and visible in the /admin/ad-reservations queue, so a
    failed email must never break the prospect's flow. Runs in a FastAPI
    BackgroundTasks slot.
    """
    try:
        from app.auth.email_sender import send_alert_email
        from app.db.database import SessionLocal

        with SessionLocal() as db:
            res = db.get(AdReservation, reservation_id)
            if res is None:
                return
            product = res.product_name
            business = res.business_name
            subject = f"New ad reservation: {product} — {business}"
            lines = [
                "A new ad-placement reservation came in via /portal/advertise.",
                "",
                f"Product: {product} ({res.product_key})",
                f"Business: {business}",
                f"Contact: {res.contact_name} <{res.contact_email}>",
                f"Phone: {res.contact_phone or '—'}",
                f"Category / notes: {res.category_or_notes or '—'}",
                "",
                "No payment was collected. Follow up to confirm and invoice.",
                "Queue: /admin/ad-reservations",
            ]
            text_body = "\n".join(lines)
            # Escape each line — ``lines`` carries unescaped user form input
            # (business/contact names, email, category/notes). Plaintext needs
            # no escaping, so ``text_body`` is left as-is.
            html_body = "<br>".join(html.escape(line) if line else "&nbsp;" for line in lines)
        operator_email = (
            os.environ.get("OPERATOR_NOTIFICATION_EMAIL") or "casey.l.solomon@gmail.com"
        )
        send_alert_email(
            to_email=operator_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )
    except Exception:  # noqa: BLE001 — best-effort; never break the reservation
        logger.exception("ad_reservation.notify_failed", extra={"reservation_id": reservation_id})


@router.get("/reserve", response_class=HTMLResponse, response_model=None)
def portal_reserve_get(
    request: Request, product: str = "", db: Session = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    """Render the reservation form for a catalog product (looked up by key).

    Unknown/blank key -> redirect back to the advertise rate card rather than
    400, so a stale or hand-typed link lands somewhere useful.
    """
    prod = products.get(product)
    if prod is None:
        return RedirectResponse(url="/portal/advertise", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="portal_reserve.html",
        context={
            "product": prod,
            "categories": _category_options() if product == "category" else None,
            "errors": {},
            "form": {},
        },
    )


@router.post("/reserve", response_class=HTMLResponse, response_model=None)
def portal_reserve_post(
    request: Request,
    background_tasks: BackgroundTasks,
    product: str = Form(...),
    business_name: str = Form(default=""),
    contact_name: str = Form(default=""),
    contact_email: str = Form(default=""),
    contact_phone: str = Form(default=""),
    category: str = Form(default=""),
    notes: str = Form(default=""),
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    """Create a pending AdReservation and fire a best-effort operator email.

    On validation failure, re-render the form with errors + preserved input
    (no row created). On success, redirect to the thank-you page (PRG).
    """
    prod = products.get(product)
    if prod is None:
        return RedirectResponse(url="/portal/advertise", status_code=303)

    business_name = business_name.strip()
    contact_name = contact_name.strip()
    contact_email = contact_email.strip()
    contact_phone = contact_phone.strip()

    errors: dict[str, str] = {}
    if not business_name:
        errors["business_name"] = "Tell us your business name."
    if not contact_name:
        errors["contact_name"] = "Who should we reach out to?"
    if not contact_email:
        errors["contact_email"] = "We need an email to confirm and invoice."
    elif not _EMAIL_RE.match(contact_email):
        errors["contact_email"] = "That email doesn't look right."

    # Category sponsorship must reference a real taxonomy slug; an unknown or
    # hand-typed value is a validation error (don't snapshot garbage).
    if product == "category" and category not in CATEGORY_LABELS:
        errors["category"] = "Pick a category from the list."

    if errors:
        return templates.TemplateResponse(
            request=request,
            name="portal_reserve.html",
            context={
                "product": prod,
                "categories": _category_options() if product == "category" else None,
                "errors": errors,
                "form": {
                    "business_name": business_name,
                    "contact_name": contact_name,
                    "contact_email": contact_email,
                    "contact_phone": contact_phone,
                    "category": category,
                    "notes": notes,
                },
            },
            status_code=400,
        )

    # For category sponsorship, snapshot the chosen category label; else notes.
    # ``category`` is a validated CATEGORY_LABELS key by this point.
    category_or_notes: str | None
    if product == "category":
        category_or_notes = CATEGORY_LABELS[category]
    else:
        category_or_notes = notes.strip() or None

    reservation = AdReservation(
        product_key=product,
        product_name=str(prod.get("name") or product),
        business_name=business_name,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone or None,
        category_or_notes=category_or_notes,
        status=AdReservationStatus.PENDING.value,
        source="advertise_page",
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)

    background_tasks.add_task(_notify_operator_of_reservation, reservation.id)
    return RedirectResponse(url="/portal/reserve/thanks", status_code=303)


@router.get("/reserve/thanks", response_class=HTMLResponse)
def portal_reserve_thanks(request: Request) -> HTMLResponse:
    """Confirmation state after a reservation is captured."""
    return templates.TemplateResponse(
        request=request, name="portal_reserve_thanks.html", context={}
    )
