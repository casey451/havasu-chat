"""2026-07-01 consolidated search fixes, Phase 2 — cuisine gates + health
specialties (ASKHAVA_SEARCH_AUDIT_2026-07-01 CONSOLIDATED §2).

Cuisine-gate coverage lives with the cuisine suites
(tests/test_cuisine_landing_pages.py, tests/test_cuisine_derivation.py). This
file covers the health-specialty routing half:

* obgyn / gynecologist / womens-health / lab terms →
  ``medical-specialists-and-imaging`` (self-activates when Phase 3 seeds it);
* pediatrician terms leave the 159-row ``primary-care`` leaf for the new
  (pending) ``pediatrics`` leaf — a no-op until seeded, never a crash;
* dermatologist keeps its existing live leaf.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.categories import leaf_pages, leaf_query
from app.db.database import Base
from app.db.models import Category, Entity, EntityCategory, Provider

# --- routing dictionary (DB-free) --------------------------------------------

_SPECIALTY_CASES = {
    "cardiologist": "medical-specialists-and-imaging",
    "podiatrist": "medical-specialists-and-imaging",
    "obgyn": "medical-specialists-and-imaging",
    "ob gyn": "medical-specialists-and-imaging",
    "ob-gyn": "medical-specialists-and-imaging",
    "obstetrician": "medical-specialists-and-imaging",
    "gynecologist": "medical-specialists-and-imaging",
    "womens health": "medical-specialists-and-imaging",
    "women's health": "medical-specialists-and-imaging",
    "lab": "medical-specialists-and-imaging",
    "labs": "medical-specialists-and-imaging",
    "medical lab": "medical-specialists-and-imaging",
    "blood work": "medical-specialists-and-imaging",
    "lab work": "medical-specialists-and-imaging",
    "pediatrician": "pediatrics",
    "pediatricians": "pediatrics",
    "pediatrics": "pediatrics",
}


def test_specialty_terms_route_to_expected_leaf() -> None:
    for raw, slug in _SPECIALTY_CASES.items():
        norm = leaf_query._normalize(raw)
        assert norm in leaf_query._QUERY_TO_LEAF, (raw, norm)
        assert leaf_query._QUERY_TO_LEAF[norm] == slug, (
            raw, norm, leaf_query._QUERY_TO_LEAF[norm],
        )


def test_pediatrician_no_longer_points_at_primary_care() -> None:
    for term in ("pediatrician", "pediatricians", "pediatrics"):
        assert leaf_query._QUERY_TO_LEAF[term] != "primary-care", term


def test_dermatologist_unchanged() -> None:
    assert leaf_query._QUERY_TO_LEAF["dermatologist"] == "dermatology-and-skin"
    assert leaf_query._QUERY_TO_LEAF["dermatologists"] == "dermatology-and-skin"


def test_pediatrics_is_declared_in_seed() -> None:
    # Phase 3 promoted pediatrics (with medical-specialists-and-imaging and
    # firearms-and-shooting-sports) from PENDING_LEAF_SLUGS into the taxonomy
    # seed; the gated data op creates the Category rows in prod.
    import json
    from pathlib import Path

    seed = json.loads(
        (Path(__file__).resolve().parents[1] / "docs" / "proposals" / "taxonomy-seed.json")
        .read_text(encoding="utf-8")
    )
    assert "pediatrics" in (seed.get("health-and-medical") or {}).get("leaves", {})
    assert "pediatrics" not in leaf_query.PENDING_LEAF_SLUGS


def test_doctor_terms_still_reach_primary_care() -> None:
    # Moving pediatrics out must not disturb the generic primary-care entries.
    assert leaf_query._QUERY_TO_LEAF["doctors"] == "primary-care"
    assert leaf_query._QUERY_TO_LEAF["family doctor"] == "primary-care"


# --- master site audit §1 — "pool supply missed 3" ----------------------------


def test_pool_supply_phrasings_route_to_pools_leaf() -> None:
    for raw in ("pool supply", "pool supplies", "pool store", "pool stores",
                "best pool supply in lake havasu"):
        norm = leaf_query._normalize(raw)
        assert norm in leaf_query._QUERY_TO_LEAF, (raw, norm)
        assert leaf_query._QUERY_TO_LEAF[norm] == "pools-and-spas", (raw, norm)


def test_pool_store_never_returns_shopping_junk() -> None:
    # The topical gate (#668) must empty a pool-less shopping bucket for "pool
    # store" — the audit's live junk was Botero Carts / Fabrics Unlimited /
    # Floral & Flirt on a "SHOPS 5 OF 12" card. DB-free: terms extraction +
    # word-boundary matching are the whole decision.
    from app.chat.intents import queries as q

    assert q._provider_activity_terms("pool store") == ["pool"]
    pat = q._topic_pattern("pool")
    for junk in ("botero golf carts", "fabrics unlimited", "floral and flirt",
                 "concierge health az"):
        assert not pat.search(junk), junk
    assert pat.search("neat pool and supply")


# --- seeded-leaf routing (isolated in-memory DB) ------------------------------


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
    "query", ["cardiologist", "obgyn", "podiatrist", "women's health", "blood work"]
)
def test_specialty_routes_once_leaf_is_seeded(mem_db: Session, query: str) -> None:
    _seed_leaf(
        mem_db,
        dept_slug="health-and-medical",
        leaf_slug="medical-specialists-and-imaging",
        n=leaf_pages.LEAF_PAGE_MIN_PROVIDERS,
    )
    leaf = leaf_query.match_leaf_query(mem_db, query)
    assert leaf is not None and leaf.slug == "medical-specialists-and-imaging", query


def test_pediatrician_routes_once_pediatrics_is_seeded(mem_db: Session) -> None:
    _seed_leaf(
        mem_db,
        dept_slug="health-and-medical",
        leaf_slug="pediatrics",
        n=leaf_pages.LEAF_PAGE_MIN_PROVIDERS,
    )
    leaf = leaf_query.match_leaf_query(mem_db, "pediatrician")
    assert leaf is not None and leaf.slug == "pediatrics"


@pytest.mark.parametrize("query", ["cardiologist", "obgyn", "pediatrician", "lab"])
def test_unseeded_specialty_stays_conversational(mem_db: Session, query: str) -> None:
    # No leaf rows at all: the mapping is a harmless no-op (falls through to the
    # conversational tiers), never a crash.
    assert leaf_query.match_leaf_query(mem_db, query) is None
