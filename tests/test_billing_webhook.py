"""P4 billing — webhook subscription lifecycle, idempotency + signature verify,
and the Customer Portal helper. Stripe is mocked (the package isn't installed);
these prove the handler logic, the route's signature gate, and that the portal
helper stays dormant until billing is enabled.
"""

from __future__ import annotations

import json
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


def _placement(db, *, provider_id, subscription_id=None, customer_id=None, session_id=None):
    p = Placement(
        provider_id=provider_id,
        placement_type="category_rank",
        category_slug="eat-drink",
        rank_tier=1,
        status=PlacementStatus.active.value,
        billing_type="recurring",
        price_cents=17900,
        stripe_subscription_id=subscription_id,
        stripe_customer_id=customer_id,
        stripe_checkout_session_id=session_id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_subscription_updated_canceled_releases_and_records() -> None:
    suf = uuid.uuid4().hex[:8]
    provider_id, sub_id = f"prov-{suf}", f"sub_{suf}"
    with SessionLocal() as db:
        p = _placement(db, provider_id=provider_id, subscription_id=sub_id)
        plid = p.id
        try:
            event = {
                "id": f"evt_{suf}",
                "type": "customer.subscription.updated",
                "data": {"object": {"id": sub_id, "status": "canceled"}},
            }
            assert service.handle_webhook_event(db, event) == "released"
            db.refresh(p)
            assert p.status == PlacementStatus.released.value
            ledger = db.scalars(
                select(RevenueEvent).where(RevenueEvent.placement_id == plid)
            ).all()
            assert len(ledger) == 1
            assert ledger[0].kind == RevenueEventKind.subscription_canceled.value
        finally:
            db.execute(delete(Placement).where(Placement.id == plid))
            db.execute(delete(RevenueEvent).where(RevenueEvent.provider_id == provider_id))
            db.commit()


def test_subscription_updated_active_keeps_live() -> None:
    suf = uuid.uuid4().hex[:8]
    provider_id, sub_id = f"prov-{suf}", f"sub_{suf}"
    with SessionLocal() as db:
        p = _placement(db, provider_id=provider_id, subscription_id=sub_id)
        p.status = PlacementStatus.pending.value
        db.commit()
        plid = p.id
        try:
            event = {
                "id": f"evt_{suf}",
                "type": "customer.subscription.updated",
                "data": {"object": {"id": sub_id, "status": "active",
                                    "cancel_at_period_end": False}},
            }
            assert service.handle_webhook_event(db, event) == "updated_active"
            db.refresh(p)
            assert p.status == PlacementStatus.active.value
        finally:
            db.execute(delete(Placement).where(Placement.id == plid))
            db.execute(delete(RevenueEvent).where(RevenueEvent.provider_id == provider_id))
            db.commit()


def test_subscription_updated_cancel_at_period_end_is_noop() -> None:
    suf = uuid.uuid4().hex[:8]
    provider_id, sub_id = f"prov-{suf}", f"sub_{suf}"
    with SessionLocal() as db:
        p = _placement(db, provider_id=provider_id, subscription_id=sub_id)
        plid = p.id
        try:
            event = {
                "id": f"evt_{suf}",
                "type": "customer.subscription.updated",
                "data": {"object": {"id": sub_id, "status": "active",
                                    "cancel_at_period_end": True}},
            }
            assert service.handle_webhook_event(db, event) == "noop"
            db.refresh(p)
            assert p.status == PlacementStatus.active.value  # unchanged until it ends
        finally:
            db.execute(delete(Placement).where(Placement.id == plid))
            db.commit()


def test_webhook_redelivery_is_idempotent() -> None:
    suf = uuid.uuid4().hex[:8]
    provider_id, sub_id = f"prov-{suf}", f"sub_{suf}"
    with SessionLocal() as db:
        p = _placement(db, provider_id=provider_id, subscription_id=sub_id)
        plid = p.id
        try:
            event = {
                "id": f"evt_{suf}",
                "type": "customer.subscription.deleted",
                "data": {"object": {"id": sub_id}},
            }
            assert service.handle_webhook_event(db, event) == "released"
            # Stripe re-delivers the same event id → no duplicate ledger row.
            assert service.handle_webhook_event(db, event) == "released"
            ledger = db.scalars(
                select(RevenueEvent).where(RevenueEvent.provider_id == provider_id)
            ).all()
            assert len(ledger) == 1
        finally:
            db.execute(delete(Placement).where(Placement.id == plid))
            db.execute(delete(RevenueEvent).where(RevenueEvent.provider_id == provider_id))
            db.commit()


# --- the route's signature gate + dispatch, with Stripe mocked --------------- #


class _FakeWebhook:
    @staticmethod
    def construct_event(payload, sig, secret):
        if sig == "bad":
            raise ValueError("invalid signature")
        return json.loads(payload)


class _FakeStripe:
    Webhook = _FakeWebhook


def _enable_mock_billing(monkeypatch) -> None:
    monkeypatch.setattr(config, "billing_enabled", lambda: True)
    monkeypatch.setattr(config, "stripe_library", lambda: _FakeStripe)
    monkeypatch.setattr(config, "stripe_webhook_secret", lambda: "whsec_test")


def test_webhook_bad_signature_400(monkeypatch) -> None:
    _enable_mock_billing(monkeypatch)
    client = TestClient(app)
    r = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "bad"})
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_signature"


def test_webhook_valid_signature_dispatches(monkeypatch) -> None:
    _enable_mock_billing(monkeypatch)
    suf = uuid.uuid4().hex[:8]
    provider_id, session_id = f"prov-{suf}", f"cs_{suf}"
    with SessionLocal() as db:
        p = _placement(db, provider_id=provider_id, session_id=session_id)
        p.status = PlacementStatus.pending.value
        db.commit()
        plid = p.id
    try:
        payload = json.dumps(
            {
                "id": f"evt_{suf}",
                "type": "checkout.session.completed",
                "data": {"object": {"id": session_id, "amount_total": 17900,
                                    "customer": f"cus_{suf}"}},
            }
        ).encode()
        client = TestClient(app)
        r = client.post("/billing/webhook", content=payload,
                        headers={"stripe-signature": "good"})
        assert r.status_code == 200
        assert r.json()["result"] == "activated"
        with SessionLocal() as db:
            assert db.get(Placement, plid).status == PlacementStatus.active.value
    finally:
        with SessionLocal() as db:
            db.execute(delete(Placement).where(Placement.id == plid))
            db.execute(delete(RevenueEvent).where(RevenueEvent.provider_id == provider_id))
            db.commit()


# --- Customer Portal helpers ------------------------------------------------- #


def test_customer_portal_dormant_returns_none(monkeypatch) -> None:
    monkeypatch.delenv("STRIPE_BILLING_ENABLED", raising=False)
    assert service.create_customer_portal_session("cus_x", return_url="/x") is None


def test_customer_id_resolution_from_placements() -> None:
    a = Placement(provider_id="p", placement_type="page_ad", price_cents=0)
    b = Placement(provider_id="p", placement_type="page_ad", price_cents=0,
                  stripe_customer_id="cus_42")
    assert service.customer_id_for_user_placements([a, b]) == "cus_42"
    assert service.customer_id_for_user_placements([a]) is None


def test_portal_route_404_when_disabled(monkeypatch) -> None:
    monkeypatch.delenv("STRIPE_BILLING_ENABLED", raising=False)
    client = TestClient(app)
    r = client.post("/billing/portal")
    assert r.status_code == 404
