"""Business portal — advertise catalog + landing (Phase 2 §5b, no payments yet)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import AdSlot, Sponsor, SponsorStatus
from app.main import app
from app.portal import products


def test_portal_landing_renders() -> None:
    with TestClient(app) as client:
        r = client.get("/portal")
    assert r.status_code == 200
    assert "/static/styles/sandstone.css" in r.text
    assert 'href="/portal/claim"' in r.text
    assert 'href="/portal/advertise"' in r.text


def test_advertise_catalog_renders_products_and_prices() -> None:
    with TestClient(app) as client:
        r = client.get("/portal/advertise")
    assert r.status_code == 200
    body = r.text
    assert "Verified &amp; Enriched Listing" in body
    assert "Category Sponsorship" in body
    assert "Gas / Utility Sponsor" in body
    assert "/ mo" in body  # monetization-range price labels render


def test_no_payment_route_yet() -> None:
    """Stripe checkout is deferred — /portal/checkout must not exist yet."""
    with TestClient(app) as client:
        r = client.get("/portal/checkout", follow_redirects=False)
    assert r.status_code == 404


def test_exclusive_gas_slot_shows_live_scarcity() -> None:
    """The gas product (marquee, cap 1) reflects the real active-sponsor count:
    available when empty, sold out when an active marquee sponsor exists."""
    with SessionLocal() as db:
        gas_before = next(p for p in products.catalog(db) if p["key"] == "gas")
        # No active marquee sponsor in a clean DB -> 1 of 1 available.
        assert gas_before["availability"]["sold_out"] is False
        assert "1 of 1 available" in gas_before["availability"]["label"]

        suf = uuid.uuid4().hex[:8]
        sp = Sponsor(
            slot=AdSlot.MARQUEE.value,
            status=SponsorStatus.APPROVED.value,
            name=f"Gas Co {suf}",
            active=True,
            cta_url="https://example.com",
            cta_label="Visit",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(sp)
        db.commit()
        try:
            gas_after = next(p for p in products.catalog(db) if p["key"] == "gas")
            assert gas_after["availability"]["sold_out"] is True
            assert "waitlist" in gas_after["availability"]["label"].lower()
        finally:
            db.execute(delete(Sponsor).where(Sponsor.id == sp.id))
            db.commit()
