"""A5 (Phase G) — read-only admin analytics over analytics_events.

Covers the admin-cookie gate and that seeded render/click telemetry surfaces on
the page (event name, slot CTR, provider attribution).
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.admin.auth import COOKIE_NAME, sign_admin_cookie
from app.analytics.events import record_event
from app.db.database import SessionLocal
from app.db.models import AnalyticsEvent, Entity, Provider
from app.main import app


def test_placement_analytics_requires_admin() -> None:
    client = TestClient(app)
    resp = client.get("/admin/placement-analytics", follow_redirects=False)
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers.get("location", "")


def test_placement_analytics_renders_seeded_telemetry() -> None:
    suf = uuid.uuid4().hex[:8]
    slot = f"testslot-{suf}"
    pname = f"A5 Analytics Biz {suf}"
    with SessionLocal() as db:
        prov = Provider(
            provider_name=pname, category="home_services", slug=f"a5-prov-{suf}",
            is_active=True, draft=False, source="test-a5",
        )
        db.add(prov)
        db.commit()
        pid = prov.id
        ent_id = prov.entity_id
        # One impression + one click on an isolated slot → CTR 100% for that slot.
        record_event(db, "home.marquee.impression", slot=slot, provider_id=pid)
        record_event(db, "sponsor.click", slot=slot, provider_id=pid)

    client = TestClient(app)
    client.cookies.set(COOKIE_NAME, sign_admin_cookie())
    try:
        resp = client.get("/admin/placement-analytics?window=all")
        assert resp.status_code == 200
        body = resp.text
        assert "surface analytics" in body
        assert "home.marquee.impression" in body  # events-by-name section
        assert slot in body  # CTR-by-slot section
        assert pname in body  # top-providers section
        assert "100.0%" in body  # the isolated slot's CTR
    finally:
        with SessionLocal() as db:
            db.execute(delete(AnalyticsEvent).where(AnalyticsEvent.provider_id == pid))
            db.execute(delete(Provider).where(Provider.id == pid))
            db.execute(delete(Entity).where(Entity.id == ent_id))
            db.commit()
