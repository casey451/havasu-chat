"""Billing HTTP surface (Stripe). Every route is gated by
:func:`app.billing.config.billing_enabled` and returns 404 while billing is
dormant, so mounting this router has zero effect on the live site today.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.billing import config, service
from app.db.database import get_db
from app.portal import placements as placement_logic

router = APIRouter(prefix="/billing", tags=["billing"])


def _require_enabled() -> None:
    if not config.billing_enabled():
        raise HTTPException(status_code=404, detail="billing_disabled")


@router.post("/checkout/{placement_id}", response_model=None)
def start_checkout(
    request: Request, placement_id: str, db: Session = Depends(get_db)
) -> RedirectResponse:
    """Merchant-initiated: start Stripe Checkout for a placement they own.
    Redirects to the hosted Stripe page. 404 while billing is dormant."""
    _require_enabled()
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="login_required")
    from app.db.monetization_models import Placement  # local: avoid import cost when unused

    placement = db.get(Placement, placement_id)
    if placement is None:
        raise HTTPException(status_code=404, detail="placement_not_found")
    if not placement_logic.owns_provider(db, user.id, placement.provider_id):
        raise HTTPException(status_code=403, detail="not_your_listing")

    base = str(request.base_url).rstrip("/")
    url = service.create_checkout_session(
        db,
        placement,
        success_url=f"{base}/portal/placements?purchased=1",
        cancel_url=f"{base}/portal/placements",
        customer_email=getattr(user, "email", None),
    )
    if not url:
        raise HTTPException(status_code=503, detail="checkout_unavailable")
    return RedirectResponse(url=url, status_code=303)


@router.post("/portal", response_model=None)
def open_customer_portal(
    request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    """Send the logged-in merchant to the Stripe-hosted Customer Portal to
    manage/cancel their placements (card, invoices, cancellation). 404 while
    billing is dormant; 303 to ``/portal/placements`` when no Stripe customer is
    held yet (nothing has been paid for)."""
    _require_enabled()
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="login_required")
    providers = placement_logic.claimed_providers(db, user.id)
    placements = placement_logic.active_placements_for_providers(
        db, [p.id for p in providers]
    )
    customer_id = service.customer_id_for_user_placements(placements)
    if not customer_id:
        return RedirectResponse(url="/portal/placements", status_code=303)
    base = str(request.base_url).rstrip("/")
    url = service.create_customer_portal_session(
        customer_id, return_url=f"{base}/portal/placements"
    )
    if not url:
        raise HTTPException(status_code=503, detail="portal_unavailable")
    return RedirectResponse(url=url, status_code=303)


@router.post("/webhook", response_model=None)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, object]:
    """Stripe webhook receiver. Verifies the signature, then applies the event
    to placements + the revenue ledger. 404 while billing is dormant."""
    _require_enabled()
    stripe = config.stripe_library()
    if stripe is None:  # pragma: no cover — guarded by _require_enabled()
        raise HTTPException(status_code=404, detail="billing_disabled")

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    secret = config.stripe_webhook_secret()
    try:
        event = stripe.Webhook.construct_event(payload, sig, secret)
    except Exception as exc:  # noqa: BLE001 — any verification failure → 400
        raise HTTPException(status_code=400, detail="invalid_signature") from exc

    result = service.handle_webhook_event(db, dict(event))
    return {"received": True, "result": result}
