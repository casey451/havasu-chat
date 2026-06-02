"""LANE B6 — GEO/AEO markup wired into the live routes.

Asserts emitted JSON-LD parses and carries required keys, that facts trace to
the catalog row / verified content (no fabrication), that absent fields are
omitted, and that canonical + meta tags are present.
"""

from __future__ import annotations

import json
import re
from datetime import date, time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.db.database import SessionLocal
from app.db.models import Entity, Event, Provider
from app.geo import faq_content
from app.main import app

_LD_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL
)


def _ld_nodes(html: str) -> list[dict]:
    out = []
    for raw in _LD_RE.findall(html):
        out.append(json.loads(raw.replace("<\\/", "</")))
    return out


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_sitemap_cache():
    main_module._sitemap_cache = None
    yield
    main_module._sitemap_cache = None


def _make_entity(db, *, source: str) -> Entity:
    ent = Entity(
        entity_type="commercial",
        slug=f"geo-ent-{uuid4().hex[:8]}",
        name="Geo Test Entity",
        source=source,
    )
    db.add(ent)
    db.flush()
    return ent


# --------------------------------------------------------------------------
# Provider profile LocalBusiness
# --------------------------------------------------------------------------
def test_provider_profile_emits_localbusiness(client: TestClient) -> None:
    slug = f"geo-prov-{uuid4().hex[:10]}"
    name = f"Geo Taproom {uuid4().hex[:6]}"
    with SessionLocal() as db:
        ent = _make_entity(db, source="test-geo")
        db.add(
            Provider(
                provider_name=name,
                category="food_drink",
                slug=slug,
                is_active=True,
                draft=False,
                source="test-geo",
                entity_id=ent.id,
                phone="(928) 846-4447",
                address="5600 Hwy 95 N #6, Lake Havasu City, AZ 86404",
                google_rating=4.8,
                google_review_count=284,
            )
        )
        db.commit()

    resp = client.get(f"/provider/{slug}")
    assert resp.status_code == 200
    nodes = [n for n in _ld_nodes(resp.text) if n.get("@type") == "LocalBusiness"]
    assert len(nodes) == 1
    node = nodes[0]
    assert node["name"] == name
    assert node["telephone"] == "(928) 846-4447"
    assert node["aggregateRating"]["ratingValue"] == 4.8
    assert node["aggregateRating"]["reviewCount"] == 284
    # canonical present
    assert 'rel="canonical"' in resp.text


def test_provider_profile_omits_rating_when_absent(client: TestClient) -> None:
    slug = f"geo-prov-{uuid4().hex[:10]}"
    with SessionLocal() as db:
        ent = _make_entity(db, source="test-geo")
        db.add(
            Provider(
                provider_name=f"No Rating Co {uuid4().hex[:6]}",
                category="services",
                slug=slug,
                is_active=True,
                draft=False,
                source="test-geo",
                entity_id=ent.id,
                google_rating=None,
                google_review_count=None,
            )
        )
        db.commit()

    resp = client.get(f"/provider/{slug}")
    assert resp.status_code == 200
    node = [n for n in _ld_nodes(resp.text) if n.get("@type") == "LocalBusiness"][0]
    assert "aggregateRating" not in node


# --------------------------------------------------------------------------
# Event permalink
# --------------------------------------------------------------------------
def test_event_permalink_emits_event_jsonld(client: TestClient) -> None:
    with SessionLocal() as db:
        ent = _make_entity(db, source="test-geo")
        ev = Event(
            title="Geo Test Concert",
            normalized_title="geo test concert",
            date=date(2030, 6, 5),
            start_time=time(19, 0),
            location_name="GraceArts Live",
            location_normalized="gracearts live",
            description="A concert.",
            event_url="https://hava.example/e",
            tags=[],
            status="live",
            source="test-geo",
            entity_id=ent.id,
        )
        db.add(ev)
        db.commit()
        eid = ev.id

    resp = client.get(f"/events/{eid}")
    assert resp.status_code == 200
    nodes = [n for n in _ld_nodes(resp.text) if n.get("@type") == "Event"]
    assert len(nodes) == 1
    node = nodes[0]
    assert node["name"] == "Geo Test Concert"
    assert node["startDate"] == "2030-06-05T19:00:00"
    assert node["location"]["name"] == "GraceArts Live"
    assert 'rel="canonical"' in resp.text


# --------------------------------------------------------------------------
# Category landing FAQPage + visible Q&A
# --------------------------------------------------------------------------
def test_category_landing_emits_faqpage_and_visible_qa(client: TestClient) -> None:
    resp = client.get("/category/eat-drink")
    assert resp.status_code == 200
    faq_nodes = [n for n in _ld_nodes(resp.text) if n.get("@type") == "FAQPage"]
    assert len(faq_nodes) == 1
    node = faq_nodes[0]
    assert node["mainEntity"], "FAQPage must carry questions"
    q0 = node["mainEntity"][0]
    assert q0["@type"] == "Question"
    assert q0["acceptedAnswer"]["@type"] == "Answer"

    # Every JSON-LD question must trace to the verified content asset.
    target = faq_content.category_faq_target("eat-drink")
    assert target is not None
    asset_questions = {f["q"] for f in target.faq_list}
    for q in node["mainEntity"]:
        assert q["name"] in asset_questions, f"unverified FAQ leaked: {q['name']}"

    # Visible Q&A block present (not just JSON-LD).
    assert "category-faq" in resp.text
    assert target.faq_list[0]["q"] in resp.text


def test_category_landing_has_canonical_and_meta(client: TestClient) -> None:
    resp = client.get("/category/eat-drink")
    assert resp.status_code == 200
    assert 'rel="canonical"' in resp.text
    assert 'property="og:url"' in resp.text
    target = faq_content.category_faq_target("eat-drink")
    assert target is not None
    assert target.meta_description in resp.text


# --------------------------------------------------------------------------
# Sitemap includes the singular SEO landing pages
# --------------------------------------------------------------------------
def test_sitemap_includes_singular_category_landings(client: TestClient) -> None:
    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert "/category/eat-drink" in resp.text
    assert "/category/on-the-water" in resp.text
