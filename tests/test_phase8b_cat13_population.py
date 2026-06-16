"""Phase 8b — cat-13 population threshold + category page smoke."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.db.database import SessionLocal
from app.db.models import Category, ContactPoint, Entity, EntityCategory, Feature, Hours, Location
from app.main import app
from scripts.ingest.lhc_civic_scrape import run_scrape
from scripts.seed_cat13_civic import run_seed

# Re-use scraper fixture for isolated population test rows
_SCRAPER_FIXTURE = """
<html><body>
<h1>Lake Havasu City Library</h1>
<p>Monday: 9:00 AM - 7:00 PM</p>
</body></html>
"""


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _count_cat13_active(db) -> int:
    cat = db.scalars(select(Category).where(Category.slug == "public-civic-resources")).one()
    return db.scalars(
        select(func.count())
        .select_from(EntityCategory)
        .join(Entity)
        .where(EntityCategory.category_id == cat.id, Entity.is_active.is_(True))
    ).one()


def _cleanup_by_source(db, source: str) -> None:
    ents = db.scalars(select(Entity).where(Entity.source == source)).all()
    eids = [e.id for e in ents]
    if not eids:
        return
    db.execute(delete(ContactPoint).where(ContactPoint.entity_id.in_(eids)))
    db.execute(delete(Hours).where(Hours.entity_id.in_(eids)))
    db.execute(delete(Feature).where(Feature.entity_id.in_(eids)))
    db.execute(delete(EntityCategory).where(EntityCategory.entity_id.in_(eids)))
    db.execute(delete(Location).where(Location.entity_id.in_(eids)))
    db.execute(delete(Entity).where(Entity.id.in_(eids)))
    db.commit()


def test_cat13_population_reaches_fifteen_after_seed_and_scrape(db) -> None:
    before = _count_cat13_active(db)
    stats_scrape = run_scrape(
        db,
        source="all",
        dry_run=False,
        fetch_html=lambda url: (
            _SCRAPER_FIXTURE
            if "mohavecountylibrary" in url
            else "<html><body>Monday route schedule Havasu Hopper airport KHII Lake Havasu Elevation 783 ft</body></html>"
        ),
    )
    stats_seed = run_seed(dry_run=False)
    after = _count_cat13_active(db)
    try:
        assert after >= 15, f"expected >=15 active cat-13 entities, got {after} (before={before})"
        assert stats_scrape["insert"] + stats_scrape["update"] + stats_scrape["noop"] >= 5
        assert stats_seed["insert"] + stats_seed["update"] + stats_seed["noop"] == 11
    finally:
        _cleanup_by_source(db, "lhc_civic_scrape")
        _cleanup_by_source(db, "seed_cat13_civic")
        db.commit()


def test_public_civic_category_page_301s_to_department(client: TestClient) -> None:
    # A.3 nav rewire + IA v2 split: the retired singular route 301s to the
    # city-and-government department (community-and-civic was split into
    # city-and-government + worship-and-nonprofits).
    r = client.get("/category/public-civic-resources", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/categories/city-and-government"


def test_run_scrape_and_seed_commit_integration(db) -> None:
    """Dry-run both scripts end-to-end without error."""
    stats_scrape = run_scrape(
        db,
        source="library",
        dry_run=True,
        fetch_html=lambda _u: _SCRAPER_FIXTURE,
    )
    assert stats_scrape["insert"] + stats_scrape["update"] + stats_scrape["noop"] >= 1
    stats_seed = run_seed(dry_run=True)
    assert stats_seed["insert"] + stats_seed["update"] + stats_seed["noop"] == 11


def test_baseline_cat13_category_exists(db) -> None:
    cat = db.scalars(select(Category).where(Category.slug == "public-civic-resources")).first()
    assert cat is not None
    # Entity count is environment-dependent (isolated pytest DB vs dev DB); category row is invariant.
    assert cat.slug == "public-civic-resources"
