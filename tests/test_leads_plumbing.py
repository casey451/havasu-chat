"""Phase B7 — pay-per-lead plumbing (DORMANT, flag-gated).

Verifies the kill switch both ways:
  * flag OFF (default): capture is a no-op (no Lead row) and the HTTP hook 404s.
  * flag ON: capture writes exactly one Lead; the endpoint records + returns it.

NO billing/payment/pricing exists in this lane — these tests only exercise
capture + attribution storage.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Entity, Lead, Provider
from app.db.seed_helpers import derive_provider_slug
from app.leads.capture import LeadInput, capture_lead, leads_enabled
from app.main import app

_SOURCE = "test-b7-leads"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


def _make_provider(name: str) -> str:
    with SessionLocal() as s:
        p = Provider(
            provider_name=name,
            category="home-services",
            slug=derive_provider_slug(s, name),
            source=_SOURCE,
            draft=False,
            is_active=True,
        )
        s.add(p)
        create_provider_and_entity(s, p)
        s.commit()
        return p.id


def _cleanup(provider_id: str) -> None:
    with SessionLocal() as s:
        for lead in s.scalars(select(Lead).where(Lead.provider_id == provider_id)).all():
            s.delete(lead)
        prov = s.get(Provider, provider_id)
        ent_id = prov.entity_id if prov else None
        if prov:
            s.delete(prov)
        s.flush()
        if ent_id:
            ent = s.get(Entity, ent_id)
            if ent:
                s.delete(ent)
        s.commit()


def test_flag_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEADS_ENABLED", raising=False)
    assert leads_enabled() is False
    for falsy in ("", "0", "false", "no", "off"):
        monkeypatch.setenv("LEADS_ENABLED", falsy)
        assert leads_enabled() is False


def test_flag_explicit_on(monkeypatch: pytest.MonkeyPatch) -> None:
    for truthy in ("1", "true", "yes", "on", "TRUE", "On"):
        monkeypatch.setenv("LEADS_ENABLED", truthy)
        assert leads_enabled() is True


def test_capture_noop_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEADS_ENABLED", raising=False)
    pid = _make_provider("Flag Off Capture Co")
    try:
        with SessionLocal() as db:
            result = capture_lead(db, LeadInput(provider_id=pid, category="home-services"))
            db.commit()
            assert result is None
            rows = db.scalars(select(Lead).where(Lead.provider_id == pid)).all()
            assert rows == []
    finally:
        _cleanup(pid)


def test_capture_writes_row_when_flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEADS_ENABLED", "1")
    pid = _make_provider("Flag On Capture Co")
    try:
        with SessionLocal() as db:
            lead = capture_lead(
                db,
                LeadInput(
                    provider_id=pid,
                    category="home-services",
                    intent_key="FIND_PLUMBER",
                    contact_name="Pat Tester",
                    contact_email="pat@example.com",
                    contact_message="Need a quote",
                ),
            )
            db.commit()
            assert lead is not None
            assert lead.status == "new"
            assert lead.intent_key == "FIND_PLUMBER"

            rows = db.scalars(select(Lead).where(Lead.provider_id == pid)).all()
            assert len(rows) == 1
            assert rows[0].contact_email == "pat@example.com"
    finally:
        _cleanup(pid)


def test_endpoint_dormant_404_when_flag_off(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LEADS_ENABLED", raising=False)
    pid = _make_provider("Endpoint Off Co")
    try:
        resp = client.post("/api/leads", json={"provider_id": pid})
        assert resp.status_code == 404
        with SessionLocal() as db:
            assert db.scalars(select(Lead).where(Lead.provider_id == pid)).all() == []
    finally:
        _cleanup(pid)


def test_endpoint_records_lead_when_flag_on(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEADS_ENABLED", "1")
    pid = _make_provider("Endpoint On Co")
    try:
        resp = client.post(
            "/api/leads",
            json={
                "provider_id": pid,
                "category": "home-services",
                "intent_key": "FIND_PLUMBER",
                "contact_name": "Sam Lead",
                "contact_phone": "555-0100",
            },
        )
        assert resp.status_code == 201
        lead_id = resp.json()["lead_id"]
        assert lead_id

        with SessionLocal() as db:
            row = db.get(Lead, lead_id)
            assert row is not None
            assert row.provider_id == pid
            assert row.contact_name == "Sam Lead"
            assert row.status == "new"
    finally:
        _cleanup(pid)


def test_endpoint_404_for_unknown_provider_when_flag_on(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEADS_ENABLED", "1")
    resp = client.post("/api/leads", json={"provider_id": str(uuid4())})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "provider_not_found"
