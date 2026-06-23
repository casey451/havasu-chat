"""Billing service layer: placement activation, the revenue ledger, Stripe
checkout creation, and webhook dispatch.

Two layers live here on purpose:

* **DB-only helpers** (:func:`activate_paid_placement`, :func:`release_placement`,
  :func:`record_revenue`) take a :class:`~sqlalchemy.orm.Session` and move no
  money. They are fully testable with a placement row and run regardless of
  whether Stripe is configured — they are what the webhook *does* once a Stripe
  event is verified, and they mirror the admin activate/release transitions in
  ``app/admin/sponsor_surface.py`` so serving behaves identically.
* **Stripe calls** (:func:`create_checkout_session`, :func:`handle_webhook_event`)
  are guarded by :func:`app.billing.config.billing_enabled` and import ``stripe``
  lazily; they are no-ops / return ``None`` while billing is dormant.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing import config
from app.db.monetization_models import (
    BillingType,
    Placement,
    PlacementStatus,
    RevenueEvent,
    RevenueEventKind,
)

DEFAULT_TERM_DAYS = 30


def _naive_utc_now() -> datetime:
    """Naive UTC, matching the stored ``DateTime`` columns elsewhere."""
    return datetime.now(UTC).replace(tzinfo=None)


# --------------------------------------------------------------------------- #
# DB-only helpers (no Stripe, no money) — the durable effects of a paid event.
# --------------------------------------------------------------------------- #


def record_revenue(
    db: Session,
    *,
    kind: str,
    amount_cents: int,
    provider_id: str | None = None,
    placement_id: str | None = None,
    currency: str = "usd",
    stripe_event_id: str | None = None,
    stripe_object_id: str | None = None,
    note: str | None = None,
) -> RevenueEvent | None:
    """Append a ledger row. Idempotent on ``stripe_event_id``: a redelivered
    webhook (same event id) is skipped and returns ``None``."""
    if stripe_event_id:
        existing = db.scalars(
            select(RevenueEvent).where(RevenueEvent.stripe_event_id == stripe_event_id)
        ).first()
        if existing is not None:
            return None
    ev = RevenueEvent(
        kind=kind,
        amount_cents=amount_cents,
        provider_id=provider_id,
        placement_id=placement_id,
        currency=currency,
        stripe_event_id=stripe_event_id,
        stripe_object_id=stripe_object_id,
        note=note,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def activate_paid_placement(
    db: Session,
    placement: Placement,
    *,
    term_days: int = DEFAULT_TERM_DAYS,
    paid_through: datetime | None = None,
) -> None:
    """Flip a placement to ``active`` and set its paid window — the same
    transition the admin activate route performs, so the serving layer treats a
    Stripe-paid placement identically to an operator-activated one."""
    now = _naive_utc_now()
    placement.status = PlacementStatus.active.value
    if placement.starts_at is None:
        placement.starts_at = now
    placement.paid_through = paid_through or (now + timedelta(days=term_days))
    db.add(placement)
    db.commit()


def release_placement(db: Session, placement: Placement) -> None:
    """Release a placement (stops serving immediately, frees the spot)."""
    placement.status = PlacementStatus.released.value
    db.add(placement)
    db.commit()


def _placement_by_stripe(
    db: Session, *, session_id: str | None = None, subscription_id: str | None = None
) -> Placement | None:
    if session_id:
        p = db.scalars(
            select(Placement).where(Placement.stripe_checkout_session_id == session_id)
        ).first()
        if p is not None:
            return p
    if subscription_id:
        return db.scalars(
            select(Placement).where(Placement.stripe_subscription_id == subscription_id)
        ).first()
    return None


# --------------------------------------------------------------------------- #
# Stripe calls (guarded by billing_enabled(); lazy import; dormant by default).
# --------------------------------------------------------------------------- #


def create_checkout_session(
    db: Session,
    placement: Placement,
    *,
    success_url: str,
    cancel_url: str,
    customer_email: str | None = None,
) -> str | None:
    """Create a Stripe Checkout Session for a pending placement and return its
    hosted URL. Returns ``None`` (no-op) while billing is dormant.

    ``recurring`` billing → a subscription-mode session; ``monthly`` (month-to-
    month, no auto-renew) → a one-time payment-mode session. The placement's
    ``stripe_checkout_session_id`` is stored so the webhook can resolve it back.
    """
    if not config.billing_enabled():
        return None
    stripe: Any = config.stripe_library()
    if stripe is None:  # pragma: no cover — guarded by billing_enabled()
        return None
    stripe.api_key = config.stripe_secret_key()

    recurring = placement.billing_type == BillingType.recurring.value
    amount = max(int(placement.price_cents or 0), 0)
    price_data: dict[str, Any] = {
        "currency": "usd",
        "unit_amount": amount,
        "product_data": {"name": f"Ask Hava placement {placement.placement_type}"},
    }
    if recurring:
        price_data["recurring"] = {"interval": "month"}
    try:
        session = stripe.checkout.Session.create(
            mode="subscription" if recurring else "payment",
            line_items=[{"price_data": price_data, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=customer_email or None,
            client_reference_id=placement.id,
            metadata={"placement_id": placement.id, "provider_id": placement.provider_id},
        )
    except Exception:  # noqa: BLE001 — a Stripe-side error must not 500 checkout
        return None
    placement.stripe_checkout_session_id = session.get("id")
    db.add(placement)
    db.commit()
    return session.get("url")


def create_customer_portal_session(
    customer_id: str, *, return_url: str
) -> str | None:
    """Create a Stripe-hosted Customer Portal session for ``customer_id`` and
    return its URL. The portal (configured no-code in the Stripe Dashboard) is
    where a merchant updates a card, downloads invoices, or cancels — a cancel
    fires ``customer.subscription.deleted`` which :func:`handle_webhook_event`
    turns into a placement release. Returns ``None`` while billing is dormant or
    when no ``customer_id`` is held."""
    if not config.billing_enabled() or not customer_id:
        return None
    stripe: Any = config.stripe_library()
    if stripe is None:  # pragma: no cover — guarded by billing_enabled()
        return None
    stripe.api_key = config.stripe_secret_key()
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id, return_url=return_url
        )
    except Exception:  # noqa: BLE001 — a Stripe-side error must not 500 the page
        return None
    return session.get("url")


def customer_id_for_user_placements(placements: list[Placement]) -> str | None:
    """The Stripe customer id held by any of a merchant's placements (the first
    found). One Stripe customer backs all of a merchant's placements once they
    have paid once, so any placement's id resolves the portal."""
    for p in placements:
        if p.stripe_customer_id:
            return p.stripe_customer_id
    return None


def handle_webhook_event(db: Session, event: dict[str, Any]) -> str:
    """Apply a verified Stripe event to placements + ledger. Returns a short
    status string for logging/tests. Unhandled event types are acknowledged
    (``"ignored"``) so Stripe stops retrying.

    Mapping:
      * ``checkout.session.completed`` → activate placement, record ``payment``
      * ``invoice.paid``               → extend paid window, record ``renewal``
      * ``invoice.payment_failed`` / ``customer.subscription.deleted`` → release
      * ``charge.refunded``            → record a negative ``refund`` entry
    """
    etype = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}
    event_id = event.get("id")

    if etype == "checkout.session.completed":
        placement = _placement_by_stripe(db, session_id=obj.get("id"))
        if placement is None:
            return "no_placement"
        sub_id = obj.get("subscription")
        if sub_id:
            placement.stripe_subscription_id = sub_id
        cust_id = obj.get("customer")
        if cust_id:
            placement.stripe_customer_id = cust_id
        activate_paid_placement(db, placement)
        record_revenue(
            db,
            kind=RevenueEventKind.payment.value,
            amount_cents=int(obj.get("amount_total") or placement.price_cents or 0),
            provider_id=placement.provider_id,
            placement_id=placement.id,
            stripe_event_id=event_id,
            stripe_object_id=obj.get("id"),
        )
        return "activated"

    if etype == "invoice.paid":
        placement = _placement_by_stripe(db, subscription_id=obj.get("subscription"))
        if placement is None:
            return "no_placement"
        activate_paid_placement(db, placement)
        record_revenue(
            db,
            kind=RevenueEventKind.renewal.value,
            amount_cents=int(obj.get("amount_paid") or 0),
            provider_id=placement.provider_id,
            placement_id=placement.id,
            stripe_event_id=event_id,
            stripe_object_id=obj.get("id"),
        )
        return "renewed"

    if etype == "customer.subscription.updated":
        # A subscription's lifecycle changed. Drive the placement off its status:
        # active/trialing → keep the spot live; a terminal/unpaid state → release
        # it. ``past_due`` is a grace state (Stripe is still retrying) — leave the
        # placement live and wait for invoice.paid / .payment_failed to decide.
        sub_id = obj.get("id")
        placement = _placement_by_stripe(db, subscription_id=sub_id)
        if placement is None:
            return "no_placement"
        status = str(obj.get("status") or "").lower()
        cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
        if status in ("active", "trialing") and not cancel_at_period_end:
            # Only entitlement-extending events (invoice.paid) move paid_through.
            # A routine/redelivered subscription.updated must NOT keep pushing the
            # paid window out — reactivate a non-active spot preserving its window,
            # and no-op when it is already active.
            if placement.status != PlacementStatus.active.value:
                activate_paid_placement(db, placement, paid_through=placement.paid_through)
            return "updated_active"
        if status in ("canceled", "unpaid", "incomplete_expired"):
            release_placement(db, placement)
            record_revenue(
                db,
                kind=RevenueEventKind.subscription_canceled.value,
                amount_cents=0,
                provider_id=placement.provider_id,
                placement_id=placement.id,
                stripe_event_id=event_id,
                stripe_object_id=sub_id,
            )
            return "released"
        # active-but-cancel_at_period_end, past_due, paused, etc.: no state change
        # here — the spot stays as-is until a terminal event arrives.
        return "noop"

    if etype in ("invoice.payment_failed", "customer.subscription.deleted"):
        sub_id = obj.get("subscription") or obj.get("id")
        placement = _placement_by_stripe(db, subscription_id=sub_id)
        if placement is None:
            return "no_placement"
        release_placement(db, placement)
        kind = (
            RevenueEventKind.lapse.value
            if etype == "invoice.payment_failed"
            else RevenueEventKind.subscription_canceled.value
        )
        record_revenue(
            db,
            kind=kind,
            amount_cents=0,
            provider_id=placement.provider_id,
            placement_id=placement.id,
            stripe_event_id=event_id,
            stripe_object_id=sub_id,
        )
        return "released"

    if etype == "charge.refunded":
        amount = int(obj.get("amount_refunded") or 0)
        record_revenue(
            db,
            kind=RevenueEventKind.refund.value,
            amount_cents=-abs(amount),
            stripe_event_id=event_id,
            stripe_object_id=obj.get("id"),
        )
        return "refunded"

    return "ignored"
