"""P5 admin cancel/refund flow — the service function (Stripe mocked), the
webhook PaymentIntent capture + charge.refunded attribution, and the admin route.

Stripe is mocked everywhere (the package isn't installed). These prove: an admin
cancel calls Stripe + releases the spot; a refund targets the captured
PaymentIntent; the webhook captures that PaymentIntent and a charge.refunded
attributes the negative ledger entry back to the placement and frees it.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.admin.auth import COOKIE_NAME, sign_admin_cookie
from app.billing import config, service
from app.db.database import SessionLocal
from app.db.monetization_models import (
    Placement,
    PlacementStatus,
    RevenueEvent,
    RevenueEventKind,
)
from app.main import app


def _placement(db, *, provider_id, subscription_id=None, payment_intent=None):
    p = Placement(
        provider_id=provider_id,
        placement_type="category_rank",
        category_slug="eat-drink",
        rank_tier=1,
        status=PlacementStatus.active.value,
        billing_type="recurring",
        price_cents=17900,
        stripe_subscription_id=subscription_id,
        stripe_payment_intent_id=payment_intent,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


class _FakeSubscription:
    @staticmethod
    def delete(sub_id):
        _FakeStripe.calls.append(("sub.delete", sub_id))
        return {"id": sub_id, "status": "canceled"}


class _FakeRefund:
    @staticmethod
    def create(**kwargs):
        _FakeStripe.calls.append(("refund.create", kwargs))
        return {"id": "re_test", "amount": 17900}


class _FakeStripe:
    api_key = None
    calls: list = []
    Subscription = _FakeSubscription
    Refund = _FakeRefund


def _enable_mock_stripe(monkeypatch) -> None:
    _FakeStripe.calls = []
    monkeypatch.setattr(config, "billing_enabled", lambda: True)
    monkeypatch.setattr(config, "stripe_library", lambda: _FakeStripe)
    monkeypatch.setattr(config, "stripe_secret_key", lambda: "sk_test")


def test_cancel_placement_dormant_releases_only(monkeypatch) -> None:
    monkeypatch.setattr(config, "billing_enabled", lambda: False)
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        p = _placement(db, provider_id=f"prov-{suf}", subscription_id=f"sub_{suf}")
        plid = p.id
        try:
            summary = service.cancel_placement(db, p, refund=True)
            assert summary["stripe_called"] is False
            db.refresh(p)
            assert p.status == PlacementStatus.released.value
        finally:
            db.execute(delete(Placement).where(Placement.id == plid))
            db.commit()


def test_cancel_placement_calls_stripe_and_refunds(monkeypatch) -> None:
    _enable_mock_stripe(monkeypatch)
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        p = _placement(
            db,
            provider_id=f"prov-{suf}",
            subscription_id=f"sub_{suf}",
            payment_intent=f"pi_{suf}",
        )
        plid = p.id
        try:
            summary = service.cancel_placement(db, p, refund=True)
            assert summary["canceled"] is True
            assert summary["refunded"] is True
            assert summary["refund_amount_cents"] == 17900
            assert ("sub.delete", f"sub_{suf}") in _FakeStripe.calls
            assert any(
                c[0] == "refund.create" and c[1].get("payment_intent") == f"pi_{suf}"
                for c in _FakeStripe.calls
            )
            db.refresh(p)
            assert p.status == PlacementStatus.released.value
        finally:
            db.execute(delete(Placement).where(Placement.id == plid))
            db.commit()


def test_cancel_refund_without_payment_intent_reports_error(monkeypatch) -> None:
    _enable_mock_stripe(monkeypatch)
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        p = _placement(db, provider_id=f"prov-{suf}", subscription_id=f"sub_{suf}")
        plid = p.id
        try:
            summary = service.cancel_placement(db, p, refund=True)
            assert summary["canceled"] is True
            assert summary["refunded"] is False
            assert any("no captured payment" in e for e in summary["errors"])
            db.refresh(p)
            assert p.status == PlacementStatus.released.value
        finally:
            db.execute(delete(Placement).where(Placement.id == plid))
            db.commit()


def test_webhook_captures_payment_intent() -> None:
    suf = uuid.uuid4().hex[:8]
    provider_id, session_id = f"prov-{suf}", f"cs_{suf}"
    with SessionLocal() as db:
        p = Placement(
            provider_id=provider_id,
            placement_type="category_rank",
            category_slug="eat-drink",
            rank_tier=1,
            status=PlacementStatus.pending.value,
            billing_type="recurring",
            price_cents=17900,
            stripe_checkout_session_id=session_id,
        )
        db.add(p)
        db.commit()
        plid = p.id
        try:
            event = {
                "id": f"evt_{suf}",
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": session_id,
                        "amount_total": 17900,
                        "customer": f"cus_{suf}",
                        "subscription": f"sub_{suf}",
                        "payment_intent": f"pi_{suf}",
                    }
                },
            }
            assert service.handle_webhook_event(db, event) == "activated"
            db.refresh(p)
            assert p.stripe_payment_intent_id == f"pi_{suf}"
        finally:
            db.execute(delete(Placement).where(Placement.id == plid))
            db.execute(delete(RevenueEvent).where(RevenueEvent.provider_id == provider_id))
            db.commit()


def test_charge_refunded_attributes_and_releases() -> None:
    suf = uuid.uuid4().hex[:8]
    provider_id, pi = f"prov-{suf}", f"pi_{suf}"
    with SessionLocal() as db:
        p = _placement(db, provider_id=provider_id, payment_intent=pi)
        plid = p.id
        try:
            event = {
                "id": f"evt_{suf}",
                "type": "charge.refunded",
                "data": {
                    "object": {
                        "id": f"ch_{suf}",
                        "payment_intent": pi,
                        "amount_refunded": 17900,
                    }
                },
            }
            assert service.handle_webhook_event(db, event) == "refunded"
            ledger = db.scalars(
                select(RevenueEvent).where(RevenueEvent.placement_id == plid)
            ).all()
            assert len(ledger) == 1
            assert ledger[0].kind == RevenueEventKind.refund.value
            assert ledger[0].amount_cents == -17900
            assert ledger[0].provider_id == provider_id
            db.refresh(p)
            assert p.status == PlacementStatus.released.value
        finally:
            db.execute(delete(Placement).where(Placement.id == plid))
            db.execute(delete(RevenueEvent).where(RevenueEvent.provider_id == provider_id))
            db.commit()


def test_admin_cancel_route_releases_placement() -> None:
    suf = uuid.uuid4().hex[:8]
    provider_id = f"prov-{suf}"
    with SessionLocal() as db:
        p = _placement(db, provider_id=provider_id, subscription_id=f"sub_{suf}")
        plid = p.id
    try:
        client = TestClient(app)
        client.cookies.set(COOKIE_NAME, sign_admin_cookie())
        r = client.post(
            f"/admin/placements/{plid}/cancel",
            data={"refund": ""},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/admin/placements"
        with SessionLocal() as db:
            assert db.get(Placement, plid).status == PlacementStatus.released.value
    finally:
        with SessionLocal() as db:
            db.execute(delete(Placement).where(Placement.id == plid))
            db.execute(delete(RevenueEvent).where(RevenueEvent.provider_id == provider_id))
            db.commit()
