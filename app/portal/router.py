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

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.provider_name import register_template_filters, register_template_globals
from app.db.database import get_db
from app.db.models import AdReservation, AdReservationStatus
from app.home.queries import CATEGORY_LABELS
from app.monetization import serving
from app.portal import placements as placement_logic
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


def _category_options(db: Session) -> list[tuple[str, str]]:
    """(slug, label) pairs for the category-sponsorship dropdown.

    Sources the CANONICAL taxonomy departments (``Category`` level-0 rows —
    the same pages the nav and /categories index render), not the legacy
    map-scope ``CATEGORY_LABELS`` list the form used to offer: that list had
    13 scopes that don't match the sellable department pages (no Beauty,
    Fitness & Wellness, Family & Education, Things to Do…) and included
    "Events", which is sold separately as Event Boost (audit §13.1 — a paying
    advertiser couldn't pick the page the product actually pins them to).
    Falls back to the legacy list on any DB hiccup so the revenue form never
    renders an empty dropdown. Order matches the nav (taxonomy sort_order).
    """
    from app.categories.leaf_pages import all_departments  # lazy: avoid import cycle

    try:
        rows = all_departments(db)
    except Exception:  # noqa: BLE001 — fall back, never blank the form
        rows = []
    if rows:
        return [(dept.slug, dept.name) for dept, _leaf_count, _total in rows]
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
            "categories": _category_options(db) if product == "category" else None,
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

    # Category sponsorship must reference a slug we actually rendered as an
    # option; an unknown or hand-typed value is a validation error (don't
    # snapshot garbage).
    option_labels = dict(_category_options(db)) if product == "category" else {}
    if product == "category" and category not in option_labels:
        errors["category"] = "Pick a category from the list."

    if errors:
        return templates.TemplateResponse(
            request=request,
            name="portal_reserve.html",
            context={
                "product": prod,
                "categories": _category_options(db) if product == "category" else None,
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
    # ``category`` is a validated option key by this point.
    category_or_notes: str | None
    if product == "category":
        category_or_notes = option_labels[category]
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


# ── self-serve placement purchase (Phase F §8; merchant-gated, NO payment yet) ─


def _indicative_prices(db: Session) -> dict:
    """Global-default prices (cents) for the buy form's rate display."""
    return {
        "homepage_rotating": serving.price_for(db, "homepage_rotating"),
        "page_ad": serving.price_for(db, "page_ad"),
        "category_rank": {
            t: serving.price_for(db, "category_rank", rank_tier=t) for t in range(1, 6)
        },
    }


@router.get("/placements", response_class=HTMLResponse, response_model=None)
def portal_placements(
    request: Request, db: Session = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    """A merchant's placement dashboard: their claimed listings + any placements
    held (pending or active). Login-gated; an unclaimed visitor is sent to claim."""
    user = get_current_user(request)
    if user is None:
        return RedirectResponse(url="/login?next=/portal/placements", status_code=303)
    providers = placement_logic.claimed_providers(db, user.id)
    placements = placement_logic.active_placements_for_providers(
        db, [p.id for p in providers]
    )
    return templates.TemplateResponse(
        request=request,
        name="portal_placements.html",
        context={
            "providers": providers,
            "placements": placements,
            "prov_by_id": {p.id: p for p in providers},
            "type_labels": {
                k: v["label"] for k, v in placement_logic.PURCHASABLE_TYPES.items()
            },
            "purchased": request.query_params.get("purchased") == "1",
        },
    )


@router.get("/placements/new", response_class=HTMLResponse, response_model=None)
def portal_placement_new_get(
    request: Request, provider_id: str = "", db: Session = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    """Render the buy-a-placement form for the merchant's claimed listings."""
    user = get_current_user(request)
    if user is None:
        return RedirectResponse(url="/login?next=/portal/placements/new", status_code=303)
    providers = placement_logic.claimed_providers(db, user.id)
    if not providers:
        return RedirectResponse(url="/portal/claim", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="portal_placement_new.html",
        context={
            "providers": providers,
            "selected_provider_id": provider_id,
            "categories": _category_options(db),
            "types": placement_logic.PURCHASABLE_TYPES,
            "prices": _indicative_prices(db),
            "creatives": _merchant_creatives(db, providers),
            "errors": {},
            "form": {},
        },
    )


@router.post("/placements/new", response_class=HTMLResponse, response_model=None)
def portal_placement_new_post(
    request: Request,
    provider_id: str = Form(...),
    placement_type: str = Form(...),
    category_slug: str = Form(default=""),
    rank_tier: str = Form(default=""),
    billing_type: str = Form(default="monthly"),
    creative_id: str = Form(default=""),
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    """Create a ``pending`` placement after checking ownership + inputs.

    No payment is taken — the placement awaits operator confirmation (and, later,
    Stripe checkout). A pending placement is not served, so this is side-effect
    free on the live site until activated.
    """
    user = get_current_user(request)
    if user is None:
        return RedirectResponse(url="/login?next=/portal/placements/new", status_code=303)
    if not placement_logic.owns_provider(db, user.id, provider_id):
        raise HTTPException(status_code=403, detail="not_your_listing")

    cat = category_slug.strip() or None
    tier_int = int(rank_tier) if rank_tier.strip().isdigit() else None
    errors = placement_logic.validate_purchase(
        placement_type, category_slug=cat, rank_tier=tier_int, billing_type=billing_type
    )
    # A category, when required, must be a real department option (not hand-typed).
    if cat is not None and "category_slug" not in errors:
        if cat not in dict(_category_options(db)):
            errors["category_slug"] = "Pick a category from the list."

    if errors:
        providers = placement_logic.claimed_providers(db, user.id)
        return templates.TemplateResponse(
            request=request,
            name="portal_placement_new.html",
            context={
                "providers": providers,
                "selected_provider_id": provider_id,
                "categories": _category_options(db),
                "types": placement_logic.PURCHASABLE_TYPES,
                "prices": _indicative_prices(db),
                "creatives": _merchant_creatives(db, providers),
                "errors": errors,
                "form": {
                    "provider_id": provider_id,
                    "placement_type": placement_type,
                    "category_slug": category_slug,
                    "rank_tier": rank_tier,
                    "billing_type": billing_type,
                    "creative_id": creative_id,
                },
            },
            status_code=400,
        )

    placement_logic.create_pending_placement(
        db,
        provider_id=provider_id,
        placement_type=placement_type,
        category_slug=cat,
        rank_tier=tier_int,
        billing_type=billing_type,
        creative_id=(creative_id.strip() or None),
    )
    return RedirectResponse(url="/portal/placements?purchased=1", status_code=303)


# ── ad creatives (URL-based; F2) ──────────────────────────────────────────────


def _merchant_creatives(db: Session, providers: list) -> list[dict]:
    """Flattened (creative, provider-name) list across a merchant's listings."""
    out: list[dict] = []
    for prov in providers:
        for c in placement_logic.creatives_for_provider(db, prov.id):
            out.append(
                {
                    "id": c.id,
                    "provider_id": prov.id,
                    "provider_name": prov.provider_name,
                    "headline": c.headline,
                    "image_url": c.image_url,
                }
            )
    return out


@router.get("/creatives", response_class=HTMLResponse, response_model=None)
def portal_creatives(
    request: Request, db: Session = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    """List the merchant's ad creatives and a form to add one (URL-based)."""
    user = get_current_user(request)
    if user is None:
        return RedirectResponse(url="/login?next=/portal/creatives", status_code=303)
    providers = placement_logic.claimed_providers(db, user.id)
    if not providers:
        return RedirectResponse(url="/portal/claim", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="portal_creatives.html",
        context={
            "providers": providers,
            "creatives": _merchant_creatives(db, providers),
            "errors": {},
            "form": {},
        },
    )


@router.post("/creatives", response_class=HTMLResponse, response_model=None)
def portal_creatives_create(
    request: Request,
    provider_id: str = Form(...),
    headline: str = Form(default=""),
    body: str = Form(default=""),
    cta_label: str = Form(default=""),
    cta_url: str = Form(default=""),
    image_url: str = Form(default=""),
    image_url_mobile: str = Form(default=""),
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    """Create a URL-based creative for a listing the merchant owns."""
    user = get_current_user(request)
    if user is None:
        return RedirectResponse(url="/login?next=/portal/creatives", status_code=303)
    if not placement_logic.owns_provider(db, user.id, provider_id):
        raise HTTPException(status_code=403, detail="not_your_listing")

    errors: dict[str, str] = {}
    if not headline.strip() and not image_url.strip():
        errors["headline"] = "Give the creative a headline or an image URL."

    if errors:
        providers = placement_logic.claimed_providers(db, user.id)
        return templates.TemplateResponse(
            request=request,
            name="portal_creatives.html",
            context={
                "providers": providers,
                "creatives": _merchant_creatives(db, providers),
                "errors": errors,
                "form": {
                    "provider_id": provider_id,
                    "headline": headline,
                    "body": body,
                    "cta_label": cta_label,
                    "cta_url": cta_url,
                    "image_url": image_url,
                    "image_url_mobile": image_url_mobile,
                },
            },
            status_code=400,
        )

    placement_logic.create_creative(
        db,
        provider_id=provider_id,
        headline=headline.strip(),
        body=body.strip(),
        cta_label=cta_label.strip(),
        cta_url=cta_url.strip(),
        image_url=image_url.strip(),
        image_url_mobile=image_url_mobile.strip(),
    )
    return RedirectResponse(url="/portal/creatives", status_code=303)
