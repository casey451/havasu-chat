"""P1.7 — visible NAP block + schema.org PostalAddress on provider pages."""

from __future__ import annotations

import json
import re
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.db.models import Entity, Location, Provider
from app.main import app
from app.providers.queries import derive_postal_address


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def nap_provider():
    """Provider with a structured Location row (street/city/state/zip/geo)."""
    suf = uuid4().hex[:8]
    with SessionLocal() as db:
        ent = Entity(
            entity_type="commercial",
            slug=f"nap-ent-{suf}",
            name=f"NAP Test {suf}",
            source="test-nap",
        )
        db.add(ent)
        db.flush()
        db.add(
            Location(
                entity_id=ent.id,
                address="2014 McCulloch Blvd N",
                city="Lake Havasu City",
                state="AZ",
                zip="86403",
                lat=34.474,
                lng=-114.343,
            )
        )
        prov = Provider(
            provider_name=f"NAP Provider {suf}",
            category="restaurant",
            slug=f"nap-provider-{suf}",
            phone="(928) 555-0142",
            google_place_id=f"test-place-{suf}",
            is_active=True,
            draft=False,
            source="test-nap",
            entity_id=ent.id,
        )
        db.add(prov)
        db.commit()
        slug = prov.slug
    try:
        yield slug
    finally:
        with SessionLocal() as db:
            for prov in db.scalars(select(Provider).where(Provider.source == "test-nap")).all():
                db.delete(prov)
            for ent in db.scalars(select(Entity).where(Entity.source == "test-nap")).all():
                db.execute(delete(Location).where(Location.entity_id == ent.id))
                db.delete(ent)
            db.commit()


def _jsonld(html_text: str) -> dict:
    m = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', html_text, re.S
    )
    assert m, "no JSON-LD block on the page"
    return json.loads(m.group(1))


def test_jsonld_has_structured_postal_address(client: TestClient, nap_provider: str) -> None:
    r = client.get(f"/provider/{nap_provider}")
    assert r.status_code == 200
    data = _jsonld(r.text)
    addr = data["address"]
    assert addr["@type"] == "PostalAddress"
    assert addr["streetAddress"] == "2014 McCulloch Blvd N"
    assert addr["addressLocality"] == "Lake Havasu City"
    assert addr["addressRegion"] == "AZ"
    assert addr["postalCode"] == "86403"
    assert addr["addressCountry"] == "US"


def test_jsonld_has_geo_when_coords_present(client: TestClient, nap_provider: str) -> None:
    r = client.get(f"/provider/{nap_provider}")
    data = _jsonld(r.text)
    geo = data["geo"]
    assert geo["@type"] == "GeoCoordinates"
    assert abs(geo["latitude"] - 34.474) < 1e-6
    assert abs(geo["longitude"] - (-114.343)) < 1e-6


def test_visible_nap_block_renders(client: TestClient, nap_provider: str) -> None:
    r = client.get(f"/provider/{nap_provider}")
    assert "<address" in r.text
    assert "2014 McCulloch Blvd N, Lake Havasu City, AZ 86403" in r.text


def test_derive_postal_address_defaults_city_state() -> None:
    """Provider-level street only (no Location row) -> LHC/AZ defaults."""

    class _P:
        address = "123 Main St"
        entity = None

    out = derive_postal_address(_P())
    assert out == {"street": "123 Main St", "city": "Lake Havasu City", "state": "AZ"}


def test_derive_postal_address_none_without_street() -> None:
    class _P:
        address = None
        entity = None

    assert derive_postal_address(_P()) is None
