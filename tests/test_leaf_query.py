"""Workstream B.3 — chat-query → leaf-page routing (conservative exact match)."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.categories import leaf_pages, leaf_query
from app.db.database import Base, SessionLocal
from app.db.models import Category, Entity, EntityCategory, Provider
from app.main import app

_SOURCE = "test-leaf-query"


# --- _normalize (pure) -------------------------------------------------------


def test_normalize_strips_locality_and_qualifiers() -> None:
    assert leaf_query._normalize("best plumbers in Lake Havasu City") == "plumbers"
    assert leaf_query._normalize("boat rentals near me") == "boat rentals"
    assert leaf_query._normalize("Med Spas") == "med spas"
    assert leaf_query._normalize("  find  hotels  ") == "hotels"


def test_normalize_leaves_descriptive_queries_unmatched() -> None:
    # A descriptive query does not collapse to a bare category term.
    norm = leaf_query._normalize("best plumber for a slab leak")
    assert norm not in leaf_query._QUERY_TO_LEAF
    norm2 = leaf_query._normalize("is there a vet open now")
    assert norm2 not in leaf_query._QUERY_TO_LEAF


# --- match_leaf_query (isolated in-memory DB) -------------------------------


@pytest.fixture
def mem_db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_plumbing(db: Session, *, n: int) -> None:
    dept = Category(slug="home-and-property-services", name="Home & Property",
                    sort_order=0, level=0)
    db.add(dept)
    db.flush()
    leaf = Category(slug="plumbing", name="Plumbing", sort_order=0, level=1,
                    parent_id=dept.id)
    db.add(leaf)
    db.flush()
    for _ in range(n):
        ent = Entity(entity_type="commercial", slug=f"e-{uuid4().hex[:8]}", name="P")
        db.add(ent)
        db.flush()
        db.add(Provider(provider_name="P", category="x", slug=f"p-{uuid4().hex[:8]}",
                        is_active=True, draft=False, entity_id=ent.id))
        db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
    db.commit()


def test_match_routes_exact_category_to_gate_clearing_leaf(mem_db: Session) -> None:
    _seed_plumbing(mem_db, n=leaf_pages.LEAF_PAGE_MIN_PROVIDERS)
    for query in ("plumbers", "plumber", "best plumbers in lake havasu city"):
        leaf = leaf_query.match_leaf_query(mem_db, query)
        assert leaf is not None and leaf.slug == "plumbing"


def test_misspelled_category_routes_via_shared_spell_layer(mem_db: Session) -> None:
    # Live repro: /chat?q=plummbers must reach the plumbing leaf (not a dead-end
    # "I don't have any plumbers listed"). The shared spell-correct layer fixes
    # the token before the navigational dict lookup.
    _seed_plumbing(mem_db, n=leaf_pages.LEAF_PAGE_MIN_PROVIDERS)
    for query in ("plummbers", "best plummbers in lake havasu", "plumer"):
        leaf = leaf_query.match_leaf_query(mem_db, query)
        assert leaf is not None and leaf.slug == "plumbing", query


def test_descriptive_query_does_not_route(mem_db: Session) -> None:
    _seed_plumbing(mem_db, n=leaf_pages.LEAF_PAGE_MIN_PROVIDERS)
    assert leaf_query.match_leaf_query(mem_db, "best plumber for a slab leak") is None
    assert leaf_query.match_leaf_query(mem_db, "who fixes water heaters") is None
    assert leaf_query.match_leaf_query(mem_db, "") is None


def test_below_gate_leaf_does_not_route(mem_db: Session) -> None:
    _seed_plumbing(mem_db, n=leaf_pages.LEAF_PAGE_MIN_PROVIDERS - 1)
    assert leaf_query.match_leaf_query(mem_db, "plumbers") is None


def test_unknown_leaf_slug_in_map_is_safe(mem_db: Session) -> None:
    # No 'plumbing' leaf seeded at all -> no route (and no crash).
    assert leaf_query.match_leaf_query(mem_db, "plumbers") is None


# --- route behavior (app DB) -------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_chat_route_redirects_exact_category(client: TestClient) -> None:
    cat_slugs = ["hps-b3", "plumbing"]
    with SessionLocal() as db:
        if db.scalars(select(Category).where(Category.slug == "plumbing")).first():
            pytest.skip("'plumbing' leaf already present")
        dept = Category(slug="hps-b3", name="Home & Property", sort_order=0, level=0)
        db.add(dept)
        db.flush()
        leaf = Category(slug="plumbing", name="Plumbing", sort_order=0, level=1,
                        parent_id=dept.id)
        db.add(leaf)
        db.flush()
        for _ in range(leaf_pages.LEAF_PAGE_MIN_PROVIDERS):
            ent = Entity(entity_type="commercial", slug=f"e-{uuid4().hex[:8]}", name="P",
                         source=_SOURCE)
            db.add(ent)
            db.flush()
            db.add(Provider(provider_name="P", category="x", slug=f"p-{uuid4().hex[:8]}",
                            is_active=True, draft=False, source=_SOURCE, entity_id=ent.id))
            db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
        db.commit()
    try:
        r = client.get("/chat", params={"q": "plumbers"}, follow_redirects=False)
        assert r.status_code == 302
        # The search term is carried onto the leaf (?q=) for query-aware ranking.
        assert r.headers["location"] == "/categories/hps-b3/plumbing?q=plumbers"
        # A descriptive query stays on the conversational chat page.
        r2 = client.get("/chat", params={"q": "what's a good plumber for a slab leak"})
        assert r2.status_code == 200
    finally:
        with SessionLocal() as db:
            for prov in db.scalars(select(Provider).where(Provider.source == _SOURCE)).all():
                db.delete(prov)
            for ent in db.scalars(select(Entity).where(Entity.source == _SOURCE)).all():
                for ec in db.scalars(
                    select(EntityCategory).where(EntityCategory.entity_id == ent.id)
                ).all():
                    db.delete(ec)
                db.delete(ent)
            for cat in db.scalars(select(Category).where(Category.slug.in_(cat_slugs))).all():
                db.delete(cat)
            db.commit()


def test_chat_route_no_query_renders_chat(client: TestClient) -> None:
    r = client.get("/chat")
    assert r.status_code == 200


# --- hunt 2026-06-10 §2 vocabulary additions ---------------------------------


def _seed_leaf(db: Session, *, dept_slug: str, leaf_slug: str, n: int) -> None:
    dept = Category(slug=dept_slug, name=dept_slug, sort_order=0, level=0)
    db.add(dept)
    db.flush()
    leaf = Category(slug=leaf_slug, name=leaf_slug, sort_order=0, level=1, parent_id=dept.id)
    db.add(leaf)
    db.flush()
    for _ in range(n):
        ent = Entity(entity_type="commercial", slug=f"e-{uuid4().hex[:8]}", name="P")
        db.add(ent)
        db.flush()
        db.add(Provider(provider_name="P", category="x", slug=f"p-{uuid4().hex[:8]}",
                        is_active=True, draft=False, entity_id=ent.id))
        db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
    db.commit()


@pytest.mark.parametrize(
    ("query", "leaf_slug"),
    [
        ("beauty salon", "hair-salons-and-barbers"),
        ("beauty salons", "hair-salons-and-barbers"),
        ("salon", "hair-salons-and-barbers"),
        ("car dealer", "car-dealerships"),
        ("car dealers", "car-dealerships"),
        ("dealership", "car-dealerships"),
        ("dealerships", "car-dealerships"),
        ("physical therapist", "physical-therapy"),
        ("physiotherapist", "physical-therapy"),
        ("physio", "physical-therapy"),
        # Havasu Lanes primary leaf verified = family-fun-and-arcades (cat id 56)
        ("bowling", "family-fun-and-arcades"),
        ("bowling alley", "family-fun-and-arcades"),
        ("bowling alleys", "family-fun-and-arcades"),
        # already mapped before this PR; hunt-flagged, so keep it pinned
        ("electrician", "electrical"),
    ],
)
def test_hunt_2026_06_10_vocabulary_routes(mem_db: Session, query: str, leaf_slug: str) -> None:
    _seed_leaf(mem_db, dept_slug=f"dept-{leaf_slug}", leaf_slug=leaf_slug,
               n=leaf_pages.LEAF_PAGE_MIN_PROVIDERS)
    leaf = leaf_query.match_leaf_query(mem_db, query)
    assert leaf is not None and leaf.slug == leaf_slug, query


# --- service-intent routing: need-shaped asks ("hvac needs repair") ----------
# The exact matcher only routes a bare category noun; these descriptive service
# asks (a category keyword + service/function filler) route via the secondary
# match_leaf_service_intent pass, while anything with a content word or two
# categories stays conservative.


def test_service_intent_slug_routes_category_plus_filler() -> None:
    slug = leaf_query._service_intent_slug
    norm = leaf_query._normalize
    assert slug(norm("hvac needs repair")) == "hvac"
    assert slug(norm("hvac repair")) == "hvac"
    assert slug(norm("my hvac is broken")) == "hvac"
    assert slug(norm("pool service repair")) == "pools-and-spas"
    assert slug(norm("auto repair shop")) == "auto-repair"
    assert slug(norm("coffee shop")) == "cafes-and-coffee"
    assert slug(norm("i need a plumber")) == "plumbing"


def test_service_intent_slug_rejects_descriptive_or_ambiguous() -> None:
    slug = leaf_query._service_intent_slug
    norm = leaf_query._normalize
    assert slug(norm("wifi password at the coffee shop")) is None  # content leftover
    assert slug(norm("best plumber for a slab leak")) is None      # content leftover
    assert slug(norm("plumber and electrician")) is None           # two leaves
    assert slug(norm("hvac")) is None                              # single token
    assert slug(norm("coffee with my friends")) is None            # content leftover


def test_service_intent_conversational_payload_guard() -> None:
    # Factual/temporal asks must NOT service-route even with a category keyword.
    # The guard reads the RAW query because _normalize strips e.g. "open now".
    assert leaf_query._has_conversational_payload("hvac repair open now") is True
    assert leaf_query._has_conversational_payload("plumber phone number") is True
    assert leaf_query._has_conversational_payload("hvac needs repair") is False


def test_service_intent_routes_to_seeded_leaf(mem_db: Session) -> None:
    _seed_leaf(mem_db, dept_slug="home-and-property-services", leaf_slug="hvac",
               n=leaf_pages.LEAF_PAGE_MIN_PROVIDERS)
    for query in ("hvac needs repair", "hvac repair", "my hvac is broken"):
        leaf = leaf_query.match_leaf_service_intent(mem_db, query)
        assert leaf is not None and leaf.slug == "hvac", query
    # conversational + descriptive still fall through
    assert leaf_query.match_leaf_service_intent(mem_db, "hvac repair open now") is None
    assert leaf_query.match_leaf_service_intent(mem_db, "wifi at the hvac place") is None


def test_service_intent_below_gate_does_not_route(mem_db: Session) -> None:
    _seed_leaf(mem_db, dept_slug="home-and-property-services", leaf_slug="hvac",
               n=leaf_pages.LEAF_PAGE_MIN_PROVIDERS - 1)
    assert leaf_query.match_leaf_service_intent(mem_db, "hvac needs repair") is None
