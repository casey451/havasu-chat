"""F4 billing scaffolding — dormancy + the DB-only effect helpers.

Two things are proven here:

1. **Dormant by default.** With no Stripe env set, ``billing_enabled()`` is
   ``False`` and every ``/billing/*`` route 404s — so mounting the router and
   shipping this code changes nothing on the live site.
2. **The effect helpers work** regardless of Stripe. ``activate_paid_placement``
   / ``release_placement`` move a placement exactly like the admin routes do,
   ``record_revenue`` is idempotent on the Stripe event id, and the webhook
   dispatcher activates a placement from a ``checkout.session.completed`` event
   (the paid → activate path) without any Stripe package installed.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.billing import config, service
from app.db.database import SessionLocal
from app.db.monetization_models import (
    Placement,
    PlacementStatus,
    RevenueEvent,
    RevenueEventKind,
)
from app.main import app


def _pending_placement(db, *, provider_id: str, session_id: str | None = None) -> Placement:
    p = Placement(
        provider_id=provider_id,
        placement_type="page_ad",
        category_slug="eat-and-drink",
        status=PlacementStatus.pending.value,
        billing_type="monthly",
        price_cents=9900,
        stripe_checkout_session_id=session_id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_billing_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("STRIPE_BILLING_ENABLED", raising=False)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    assert config.billing_flag_on() is False
    assert config.billing_enabled() is False


def test_webhook_route_404_when_disabled(monkeypatch) -> None:
    monkeypatch.delenv("STRIPE_BILLING_ENABLED", raising=False)
    client = TestClient(app)
    r = client.post(
        "/billing/webhook", content=b"{}", headers={"stripe-signature": "t=1,v1=x"}
    )
    assert r.status_code == 404


def test_checkout_route_404_when_disabled(monkeypatch) -> None:
    monkeypatch.delenv("STRIPE_BILLING_ENABLED", raising=False)
    client = TestClient(app)
    r = client.post("/billing/checkout/anything")
    assert r.status_code == 404


def test_activate_release_and_ledger_idempotency() -> None:
    suf = uuid.uuid4().hex[:8]
    provider_id = f"prov-{suf}"
    with SessionLocal() as db:
        p = _pending_placement(db, provider_id=provider_id)
        plid = p.id
        try:
            service.activate_paid_placement(db, p, term_days=30)
            assert p.status == PlacementStatus.active.value
            assert p.starts_at is not None
            assert p.paid_through is not None

            ev = service.record_revenue(
                db,
                kind=RevenueEventKind.payment.value,
                amount_cents=9900,
                provider_id=provider_id,
                placement_id=plid,
                stripe_event_id=f"evt_{suf}",
            )
            assert ev is not None
            # Redelivery (same event id) is skipped.
            dup = service.record_revenue(
                db,
                kind=RevenueEventKind.payment.value,
                amount_cents=9900,
                stripe_event_id=f"evt_{suf}",
            )
            assert dup is None

            service.release_placement(db, p)
            assert p.status == PlacementStatus.released.value
        finally:
            db.execute(delete(Placement).where(Placement.id == plid))
            db.execute(delete(RevenueEvent).where(RevenueEvent.provider_id == provider_id))
            db.commit()


def test_webhook_checkout_completed_activates_and_records() -> None:
    suf = uuid.uuid4().hex[:8]
    provider_id = f"prov-{suf}"
    session_id = f"cs_test_{suf}"
    with SessionLocal() as db:
        p = _pending_placement(db, provider_id=provider_id, session_id=session_id)
        plid = p.id
        try:
            event = {
                "id": f"evt_{suf}",
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": session_id,
                        "amount_total": 9900,
                        "subscription": None,
                        "customer": f"cus_{suf}",
                    }
                },
            }
            result = service.handle_webhook_event(db, event)
            assert result == "activated"
            db.refresh(p)
            assert p.status == PlacementStatus.active.value
            assert p.stripe_customer_id == f"cus_{suf}"

            ledger = db.scalars(
                select(RevenueEvent).where(RevenueEvent.placement_id == plid)
            ).all()
            assert len(ledger) == 1
            assert ledger[0].kind == RevenueEventKind.payment.value
            assert ledger[0].amount_cents == 9900
        finally:
            db.execute(delete(Placement).where(Placement.id == plid))
            db.execute(delete(RevenueEvent).where(RevenueEvent.provider_id == provider_id))
            db.commit()
