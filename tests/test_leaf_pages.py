"""Workstream B.1 — generalized taxonomy leaf pages.

Covers resolve_leaf (department/leaf slug resolution against the level-0/level-1
tree), the category_id + is_primary listing join, the >=3 thin-page gate, the
route 404 matrix, and the leaf JSON-LD (BreadcrumbList + ItemList, no
AggregateRating per D4).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.categories import leaf_pages
from app.categories.router import _group_cards_by_neighborhood
from app.db.database import Base, SessionLocal
from app.db.models import Category, Entity, EntityCategory, Provider
from app.main import app

_SOURCE = "test-leaf-pages"
_JSONLD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)


# --- resolve_leaf unit (isolated in-memory DB) ------------------------------


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


def _make_tree(db: Session) -> tuple[Category, Category]:
    dept = Category(slug="home-and-property-services", name="Home & Property Services",
                    sort_order=0, level=0)
    db.add(dept)
    db.flush()
    leaf = Category(slug="plumbing", name="Plumbing", sort_order=0, level=1,
                    parent_id=dept.id)
    db.add(leaf)
    db.commit()
    return dept, leaf


def test_resolve_leaf_valid(mem_db: Session) -> None:
    _make_tree(mem_db)
    leaf = leaf_pages.resolve_leaf(mem_db, "home-and-property-services", "plumbing")
    assert leaf is not None
    assert leaf.slug == "plumbing" and leaf.name == "Plumbing"
    assert leaf.department_slug == "home-and-property-services"


def test_resolve_leaf_case_insensitive(mem_db: Session) -> None:
    _make_tree(mem_db)
    assert leaf_pages.resolve_leaf(mem_db, "Home-And-Property-Services", "PLUMBING")


def test_resolve_leaf_wrong_department_is_none(mem_db: Session) -> None:
    _make_tree(mem_db)
    # Right leaf slug, wrong department parent.
    assert leaf_pages.resolve_leaf(mem_db, "eat-and-drink", "plumbing") is None


def test_resolve_leaf_unknown_leaf_is_none(mem_db: Session) -> None:
    _make_tree(mem_db)
    assert leaf_pages.resolve_leaf(mem_db, "home-and-property-services", "nope") is None


def test_resolve_leaf_department_slug_is_not_a_leaf(mem_db: Session) -> None:
    _make_tree(mem_db)
    # The department (level 0) is not itself resolvable as a leaf.
    assert leaf_pages.resolve_leaf(mem_db, "home-and-property-services",
                                   "home-and-property-services") is None


# --- route + listing + gate (app DB) ----------------------------------------


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _seed_leaf_with_providers(db: Session, *, dept_slug: str, leaf_slug: str,
                              leaf_name: str, n: int) -> list[str]:
    """Seed a dept+leaf and ``n`` active providers primary-linked at the leaf."""
    dept = Category(slug=dept_slug, name=leaf_name + " Dept", sort_order=0, level=0)
    db.add(dept)
    db.flush()
    leaf = Category(slug=leaf_slug, name=leaf_name, sort_order=0, level=1,
                    parent_id=dept.id)
    db.add(leaf)
    db.flush()
    names: list[str] = []
    for i in range(n):
        name = f"{leaf_name} Biz {i} {uuid4().hex[:6]}"
        ent = Entity(entity_type="commercial", slug=f"leaf-ent-{uuid4().hex[:10]}",
                     name=name, source=_SOURCE)
        db.add(ent)
        db.flush()
        db.add(Provider(provider_name=name, category="x", slug=f"leaf-prov-{uuid4().hex[:10]}",
                        is_active=True, draft=False, source=_SOURCE, entity_id=ent.id,
                        google_rating=4.5, google_review_count=20))
        db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
        names.append(name)
    db.commit()
    return names


@pytest.fixture
def seeded_leaves() -> Iterator[dict]:
    """A gate-clearing leaf (3 listings) and an empty, sub-gate leaf (0).

    With the publish gate at 1 (every category is its own indexable page), the
    only below-gate state is a genuinely empty leaf, which still 404s.
    """
    suf = uuid4().hex[:6]
    ship_dept = f"ship-dept-{suf}"
    ship_leaf = f"ship-leaf-{suf}"
    thin_dept = f"thin-dept-{suf}"
    thin_leaf = f"thin-leaf-{suf}"
    cat_slugs = [ship_dept, ship_leaf, thin_dept, thin_leaf]
    with SessionLocal() as db:
        ship_names = _seed_leaf_with_providers(
            db, dept_slug=ship_dept, leaf_slug=ship_leaf, leaf_name="Plumbing",
            n=3)
        thin_names = _seed_leaf_with_providers(
            db, dept_slug=thin_dept, leaf_slug=thin_leaf, leaf_name="Falconry",
            n=leaf_pages.LEAF_PAGE_MIN_PROVIDERS - 1)
    try:
        yield {
            "ship_dept": ship_dept, "ship_leaf": ship_leaf, "ship_names": ship_names,
            "thin_dept": thin_dept, "thin_leaf": thin_leaf, "thin_names": thin_names,
        }
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


def test_leaf_page_resolves_and_lists_primary_entities(
    client: TestClient, seeded_leaves: dict
) -> None:
    r = client.get(f"/categories/{seeded_leaves['ship_dept']}/{seeded_leaves['ship_leaf']}")
    assert r.status_code == 200
    body = r.text
    for name in seeded_leaves["ship_names"]:
        assert name in body
    # H1 carries the live count and the leaf label.
    n = len(seeded_leaves["ship_names"])
    assert f"<h1>{n} Best Plumbing in Lake Havasu City, AZ</h1>" in body


def test_leaf_below_gate_404s(client: TestClient, seeded_leaves: dict) -> None:
    assert len(seeded_leaves["thin_names"]) < leaf_pages.LEAF_PAGE_MIN_PROVIDERS
    r = client.get(f"/categories/{seeded_leaves['thin_dept']}/{seeded_leaves['thin_leaf']}")
    assert r.status_code == 404


def test_leaf_unknown_department_404s(client: TestClient, seeded_leaves: dict) -> None:
    r = client.get(f"/categories/no-such-dept/{seeded_leaves['ship_leaf']}")
    assert r.status_code == 404


def test_leaf_wrong_department_for_leaf_404s(client: TestClient, seeded_leaves: dict) -> None:
    # ship_leaf is real but not under thin_dept.
    r = client.get(f"/categories/{seeded_leaves['thin_dept']}/{seeded_leaves['ship_leaf']}")
    assert r.status_code == 404


def test_leaf_page_jsonld_breadcrumb_itemlist_no_aggregate_rating(
    client: TestClient, seeded_leaves: dict
) -> None:
    r = client.get(f"/categories/{seeded_leaves['ship_dept']}/{seeded_leaves['ship_leaf']}")
    assert r.status_code == 200
    body = r.text
    blocks = [json.loads(m) for m in _JSONLD_RE.findall(body)]
    types = {b.get("@type") for b in blocks}
    assert "BreadcrumbList" in types
    assert "ItemList" in types
    ilist = next(b for b in blocks if b["@type"] == "ItemList")
    assert ilist["numberOfItems"] == len(seeded_leaves["ship_names"])
    for entry in ilist["itemListElement"]:
        assert entry["url"].startswith("http")
        assert "/provider/" in entry["url"]
    # D4: no self-serving structured ratings anywhere.
    assert "AggregateRating" not in body
    assert "aggregateRating" not in body


def test_leaf_listing_keys_on_primary_only(
    client: TestClient, seeded_leaves: dict
) -> None:
    """A non-primary entity_categories link at the leaf must NOT list."""
    extra_name = f"Secondary Co {uuid4().hex[:6]}"
    with SessionLocal() as db:
        leaf = db.scalars(
            select(Category).where(Category.slug == seeded_leaves["ship_leaf"])
        ).one()
        ent = Entity(entity_type="commercial", slug=f"leaf-ent-{uuid4().hex[:10]}",
                     name=extra_name, source=_SOURCE)
        db.add(ent)
        db.flush()
        db.add(Provider(provider_name=extra_name, category="x",
                        slug=f"leaf-prov-{uuid4().hex[:10]}", is_active=True, draft=False,
                        source=_SOURCE, entity_id=ent.id, google_rating=4.0,
                        google_review_count=10))
        # is_primary=False -> should be excluded from the leaf listing.
        db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=False))
        db.commit()
    r = client.get(f"/categories/{seeded_leaves['ship_dept']}/{seeded_leaves['ship_leaf']}")
    assert r.status_code == 200
    assert extra_name not in r.text


# --- B.2: department landings + breadcrumb upgrade + sitemap -----------------


@pytest.fixture(autouse=True)
def _clear_sitemap_cache() -> Iterator[None]:
    from app import main as main_module

    main_module._sitemap_cache.clear()
    yield
    main_module._sitemap_cache.clear()


def test_department_landing_lists_gate_clearing_leaves(
    client: TestClient, seeded_leaves: dict
) -> None:
    r = client.get(f"/categories/{seeded_leaves['ship_dept']}")
    assert r.status_code == 200
    body = r.text
    # The gate-clearing child leaf is linked by name. Phase 7.3 removed the
    # per-leaf "N listed" inventory count site-wide, so we assert the link +
    # name only (the count clause is intentionally gone).
    assert f'href="/categories/{seeded_leaves["ship_dept"]}/{seeded_leaves["ship_leaf"]}"' in body
    assert "Plumbing" in body


def test_department_landing_all_subgate_404s(
    client: TestClient, seeded_leaves: dict
) -> None:
    # thin_dept's only child leaf is below the gate -> nothing shippable -> 404.
    r = client.get(f"/categories/{seeded_leaves['thin_dept']}")
    assert r.status_code == 404


def test_leaf_breadcrumb_links_department(
    client: TestClient, seeded_leaves: dict
) -> None:
    r = client.get(f"/categories/{seeded_leaves['ship_dept']}/{seeded_leaves['ship_leaf']}")
    assert r.status_code == 200
    # Three-level crumb now links the department landing.
    assert f'href="/categories/{seeded_leaves["ship_dept"]}"' in r.text
    blocks = [json.loads(m) for m in _JSONLD_RE.findall(r.text)]
    crumb = next(b for b in blocks if b.get("@type") == "BreadcrumbList")
    assert [it["position"] for it in crumb["itemListElement"]] == [1, 2, 3]


def test_sitemap_includes_gate_leaf_and_department_excludes_thin(
    client: TestClient, seeded_leaves: dict
) -> None:
    from app import main as main_module

    r = client.get("/sitemap-pages.xml")
    assert r.status_code == 200
    xml = r.text
    base = main_module._base_url()
    assert f"{base}/categories/{seeded_leaves['ship_dept']}/{seeded_leaves['ship_leaf']}" in xml
    assert f"{base}/categories/{seeded_leaves['ship_dept']}" in xml
    # Sub-gate leaf + its (empty) department are excluded.
    assert f"{base}/categories/{seeded_leaves['thin_dept']}/{seeded_leaves['thin_leaf']}" not in xml


def test_qualifying_and_department_leaves(mem_db: Session) -> None:
    dept, leaf = _make_tree(mem_db)
    # 3 providers at the leaf -> clears the gate.
    for _ in range(3):
        ent = Entity(entity_type="commercial", slug=f"e-{uuid4().hex[:8]}",
                     name="X", source=_SOURCE)
        mem_db.add(ent)
        mem_db.flush()
        mem_db.add(Provider(provider_name="X", category="x", slug=f"p-{uuid4().hex[:8]}",
                            is_active=True, draft=False, entity_id=ent.id))
        mem_db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
    mem_db.commit()
    qual = leaf_pages.qualifying_leaves(mem_db)
    assert any(lf.slug == "plumbing" and n == 3 for lf, n in qual)
    assert leaf_pages.resolve_department(mem_db, "home-and-property-services") is not None
    dleaves = leaf_pages.department_leaves(mem_db, dept)
    assert [(lf.slug, n) for lf, n in dleaves] == [("plumbing", 3)]


# --- Cross-listing count honesty (leaf header == department landing == gate) -


def test_cross_listed_cards_render_but_do_not_inflate_count(
    mem_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A curated cross-listing renders on the leaf but is NOT a member of it.

    The "N Best X" header, the thin-page gate, and the department landing all
    count the PRIMARY entity_categories link (a business belongs to exactly one
    leaf). A cross-listed reference card — whose canonical home is its OWN leaf —
    must therefore appear on the page yet leave the count untouched, so the leaf
    header can never over-state vs the department landing for the same leaf.
    """
    from datetime import datetime

    from app.categories import cross_listing

    # A gate-clearing "boat repair" leaf with 3 native primary members.
    dept = Category(slug="otw-x", name="On the Water", sort_order=0, level=0)
    mem_db.add(dept)
    mem_db.flush()
    leaf = Category(slug="boat-repair-x", name="Boat Repair", sort_order=0,
                    level=1, parent_id=dept.id)
    mem_db.add(leaf)
    mem_db.flush()
    for i in range(3):
        ent = Entity(entity_type="commercial", slug=f"native-{i}",
                     name=f"Native Boat Repair {i}", source=_SOURCE)
        mem_db.add(ent)
        mem_db.flush()
        mem_db.add(Provider(provider_name=f"Native Boat Repair {i}", category="x",
                            slug=f"np-{i}", is_active=True, draft=False, source=_SOURCE,
                            entity_id=ent.id, google_rating=4.5, google_review_count=20))
        mem_db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))

    # A hybrid shop whose PRIMARY leaf is Auto Repair (a different department).
    auto_dept = Category(slug="auto-x", name="Auto", sort_order=1, level=0)
    mem_db.add(auto_dept)
    mem_db.flush()
    auto_leaf = Category(slug="auto-repair-x", name="Auto Repair", sort_order=0,
                         level=1, parent_id=auto_dept.id)
    mem_db.add(auto_leaf)
    mem_db.flush()
    cross_ent = Entity(entity_type="commercial", slug="hybrid-auto-marine",
                       name="Hybrid Auto Marine Service", source=_SOURCE)
    mem_db.add(cross_ent)
    mem_db.flush()
    mem_db.add(Provider(provider_name="Hybrid Auto Marine Service", category="x",
                        slug="xp-cross", is_active=True, draft=False, source=_SOURCE,
                        entity_id=cross_ent.id, google_rating=4.7, google_review_count=40))
    mem_db.add(EntityCategory(entity_id=cross_ent.id, category_id=auto_leaf.id,
                              is_primary=True))
    mem_db.commit()

    # Curate the hybrid onto the boat-repair leaf (as the real map does).
    monkeypatch.setitem(
        cross_listing.CROSS_LISTED_ENTITY_SLUGS,
        "boat-repair-x",
        frozenset({"hybrid-auto-marine"}),
    )

    leaf_obj = leaf_pages.resolve_leaf(mem_db, "otw-x", "boat-repair-x")
    assert leaf_obj is not None
    cards, total, providers = leaf_pages.leaf_listing(
        mem_db, leaf_obj, now=datetime(2026, 6, 27, 12, 0, 0)
    )

    names = [c.get("name") for c in cards]
    # The cross-listed shop RENDERS (a visible reference)...
    assert "Hybrid Auto Marine Service" in names
    # ...but does NOT count toward the canonical "N Best X" / gate total.
    assert total == 3
    # The ItemList JSON-LD basis is native members only — no cross-leaf double
    # count (cross-listed providers omitted).
    assert len(providers) == 3
    assert all(p.entity_id != cross_ent.id for p in providers)

    # The header/gate total agrees with the department landing for this leaf.
    dleaves = dict((lf.slug, n) for lf, n in leaf_pages.department_leaves(mem_db, dept))
    assert dleaves["boat-repair-x"] == total == 3


# --- B.2: Wave-1 curated per-leaf copy --------------------------------------


def test_wave1_leaf_copy_intros_and_faq_counts() -> None:
    from app.categories.leaf_copy import LEAF_COPY

    # This branch's SEO-copy batch — 9 Auto/RV/Marine + 9 Health + 6 Pets + 12
    # thin (36 leaves) — on top of the 14 Wave-1 + 5 trade entries, MERGED with the
    # leaves main added since it opened (vacation-rentals, tattoo-and-piercing,
    # mortgage-lenders, …). 59 total, no duplicate keys.
    assert len(LEAF_COPY) == 59
    for slug, copy in LEAF_COPY.items():
        words = len(copy.intro.split())
        assert 40 <= words <= 100, f"{slug}: intro is {words} words"
        assert 4 <= len(copy.faqs) <= 6, f"{slug}: {len(copy.faqs)} FAQs"


def test_copy_for_leaf_unknown_is_none() -> None:
    from app.categories.leaf_copy import copy_for_leaf

    assert copy_for_leaf("definitely-not-a-leaf") is None
    assert copy_for_leaf(None) is None
    assert copy_for_leaf("plumbing") is not None


def test_tattoo_leaf_has_curated_copy() -> None:
    """P7 polish: the tattoo leaf no longer falls back to the generic intro."""
    from app.categories.leaf_copy import copy_for_leaf

    cp = copy_for_leaf("tattoo-and-piercing")
    assert cp is not None
    assert "Lake Havasu" in cp.intro
    # 4 common FAQs + 2 tattoo-specific ones.
    assert len(cp.faqs) == 6
    questions = " ".join(q for q, _ in cp.faqs).lower()
    assert "tattoo" in questions and "piercing" in questions


def test_curated_leaf_page_renders_intro_and_faqs(client: TestClient) -> None:
    """A Wave-1 leaf (slug 'plumbing') renders its curated intro + FAQ block."""

    suf = uuid4().hex[:6]
    dept_slug = f"hps-{suf}"
    cat_slugs = [dept_slug, "plumbing"]
    with SessionLocal() as db:
        # Skip if a 'plumbing' leaf already exists in this DB (avoid slug clash).
        if db.scalars(select(Category).where(Category.slug == "plumbing")).first():
            pytest.skip("'plumbing' leaf already present in this DB")
        names = _seed_leaf_with_providers(
            db, dept_slug=dept_slug, leaf_slug="plumbing", leaf_name="Plumbing",
            n=leaf_pages.LEAF_PAGE_MIN_PROVIDERS)
    try:
        r = client.get(f"/categories/{dept_slug}/plumbing")
        assert r.status_code == 200
        body = r.text
        # Curated intro fragment present (not the generic fallback).
        assert "Desert water is hard on pipes" in body
        assert "The {n} listings below are ranked" not in body
        # FAQ block rendered (4-6 items), with the live count interpolated.
        n_faq = body.count('class="faq-item"')
        assert 4 <= n_faq <= 6
        # SEO PR-B: templated copy fills with the searcher noun ("plumbers"),
        # not the internal taxonomy label ("plumbing").
        assert f"lists {len(names)} plumbers" in body
        # Title/H1 target the searcher's word.
        assert "Best Plumbers in Lake Havasu City, AZ" in body
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


# --- G Tier-3: category-claim slot on leaf pages ----------------------------


def test_leaf_page_has_category_claim_slot(client: TestClient, seeded_leaves: dict) -> None:
    r = client.get(f"/categories/{seeded_leaves['ship_dept']}/{seeded_leaves['ship_leaf']}")
    assert r.status_code == 200
    body = r.text
    assert "cat-sponsor-claim" in body
    # P4: the advertise CTA now routes to the public /sponsor storefront (the
    # clean public purchase path) rather than the auth-gated dashboard.
    assert "/sponsor" in body
    assert "Own the Plumbing spot" in body  # ship_leaf name is "Plumbing"
    # P0 render-bug guards: a real leaf body is non-blank, and the "Can't decide?"
    # ask-strip + the category-claim CTA each render exactly once (the live site
    # showed a triple-printed ask CTA + stray duplicate fragments).
    assert len(body) > 1000
    assert body.count("Can&#39;t decide?") + body.count("Can't decide?") == 1
    # WS3.3: paid category placement is "Sponsor this category" (the free flow
    # keeps the "Claim" verb); the CTA still renders exactly once.
    assert body.count("Sponsor this category") == 1
    assert "Claim this category" not in body


def test_leaf_claim_slot_renders_above_the_listings(
    client: TestClient, seeded_leaves: dict
) -> None:
    # P3 finding 34: the unsold "claim this category" CTA holds the TOP ad slot
    # (above the listing grid), consistent with the other templates — it used to
    # sit at the very bottom of leaf pages. (?theme=lake = the live default skin.)
    base = f"/categories/{seeded_leaves['ship_dept']}/{seeded_leaves['ship_leaf']}"
    r = client.get(f"{base}?theme=lake")
    assert r.status_code == 200
    body = r.text
    claim_pos = body.find("cat-sponsor")
    grid_pos = body.find('class="listcard"')
    assert claim_pos != -1 and grid_pos != -1
    assert claim_pos < grid_pos, "claim CTA must render above the listing grid"


def test_leaf_sort_chips_separate_featured_from_top_rated(
    client: TestClient, seeded_leaves: dict
) -> None:
    # P4 follow-up: the bare route is the daily-shuffle "Featured" default, so the
    # "Top rated" chip must carry ?sort=favorites (not link to the bare URL).
    base = f"/categories/{seeded_leaves['ship_dept']}/{seeded_leaves['ship_leaf']}"
    body = client.get(f"{base}?theme=lake").text
    assert ">Featured</a>" in body
    assert ">Top rated</a>" in body
    assert "sort=favorites" in body


def test_leaf_askstrip_label_is_descriptive_not_duplicated(
    client: TestClient, seeded_leaves: dict
) -> None:
    # The ask-strip's visually-hidden <label> used to read "Ask Hava" — redundant
    # with the submit button. It now describes the field instead.
    base = f"/categories/{seeded_leaves['ship_dept']}/{seeded_leaves['ship_leaf']}"
    body = client.get(f"{base}?theme=lake").text
    assert '<label class="skip" for="trade-ask">Ask about' in body


def test_leaf_faq_render_strips_markdown(
    client: TestClient, seeded_leaves: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Finding 7 / P0 extension: the data-side guard (test_faq_copy_no_markdown)
    # only checks the curated source. This pins the RENDER path: even if markdown
    # slips into the copy, the leaf page strips it before it reaches the <h3>/<p>.
    from app.categories import leaf_copy

    slug = seeded_leaves["ship_leaf"]
    md_copy = leaf_copy.LeafCopy(
        intro="### Intro with **bold** and `code` markers.",
        faqs=(
            ("### How many {name_lower} are there?", "**Bold** answer with `code`."),
        ),
    )
    monkeypatch.setitem(leaf_copy.LEAF_COPY, slug, md_copy)
    r = client.get(f"/categories/{seeded_leaves['ship_dept']}/{slug}?theme=lake")
    assert r.status_code == 200
    body = r.text
    # The FAQ + intro render, but the markdown markers are gone.
    assert "How many" in body  # FAQ question still rendered
    assert "### " not in body
    assert "**bold**" not in body
    assert "`code`" not in body


# --- Provider-less place entities render + count toward the gate -------------


def _seed_dept_leaf(db: Session, dept_slug: str, leaf_slug: str, leaf_name: str) -> Category:
    dept = Category(slug=dept_slug, name=leaf_name + " Dept", sort_order=0, level=0)
    db.add(dept)
    db.flush()
    leaf = Category(slug=leaf_slug, name=leaf_name, sort_order=0, level=1, parent_id=dept.id)
    db.add(leaf)
    db.flush()
    return leaf


def _add_place(db: Session, leaf: Category, name: str) -> None:
    """An active entity with a primary leaf link but NO Provider (a place)."""
    ent = Entity(entity_type="place", slug=f"place-{uuid4().hex[:10]}", name=name,
                 source=_SOURCE)
    db.add(ent)
    db.flush()
    db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))


@pytest.fixture
def _place_cleanup() -> Iterator[list[str]]:
    cat_slugs: list[str] = []
    yield cat_slugs
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


def test_provider_less_places_render_and_count(
    client: TestClient, _place_cleanup: list[str]
) -> None:
    suf = uuid4().hex[:6]
    dept_slug, leaf_slug = f"otw-{suf}", f"kayak-{suf}"
    _place_cleanup.extend([dept_slug, leaf_slug])
    with SessionLocal() as db:
        leaf = _seed_dept_leaf(db, dept_slug, leaf_slug, "Kayak & Paddle")
        # 1 provider-backed + 2 provider-less places = 3 renderable -> clears gate.
        ent = Entity(entity_type="commercial", slug=f"e-{uuid4().hex[:8]}",
                     name="Channel Kayak Rentals", source=_SOURCE)
        db.add(ent)
        db.flush()
        db.add(Provider(provider_name="Channel Kayak Rentals", category="x",
                        slug=f"p-{uuid4().hex[:8]}", is_active=True, draft=False,
                        source=_SOURCE, entity_id=ent.id, google_rating=4.6,
                        google_review_count=30))
        db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
        _add_place(db, leaf, "Three Dunes Paddle Launch")
        _add_place(db, leaf, "Windsor Beach Put-In")
        db.commit()

    r = client.get(f"/categories/{dept_slug}/{leaf_slug}")
    assert r.status_code == 200
    body = r.text
    # H1 count is the full renderable set (1 provider + 2 places).
    assert "<h1>3 Best Kayak &amp; Paddle in Lake Havasu City, AZ</h1>" in body
    # The provider-backed card links; the place cards render non-linking.
    assert "Channel Kayak Rentals" in body
    assert "Three Dunes Paddle Launch" in body
    assert "Windsor Beach Put-In" in body
    # Only the provider-backed card links to a /provider/ detail page (its name +
    # "View" button = 2 links); the two provider-less places add no provider link.
    assert body.count('href="/provider/') == 2


def test_place_only_leaf_gate(client: TestClient, _place_cleanup: list[str]) -> None:
    """A leaf with only place entities still ships once >=3 render."""
    suf = uuid4().hex[:6]
    dept_slug, leaf_slug = f"civic-{suf}", f"libraries-{suf}"
    _place_cleanup.extend([dept_slug, leaf_slug])
    with SessionLocal() as db:
        leaf = _seed_dept_leaf(db, dept_slug, leaf_slug, "Libraries")
        for nm in ("Main Library", "Branch Library", "Law Library"):
            _add_place(db, leaf, nm)
        db.commit()
    r = client.get(f"/categories/{dept_slug}/{leaf_slug}")
    assert r.status_code == 200
    assert "<h1>3 Best Libraries in Lake Havasu City, AZ</h1>" in r.text


def test_place_only_leaf_below_gate_404s(client: TestClient, _place_cleanup: list[str]) -> None:
    suf = uuid4().hex[:6]
    dept_slug, leaf_slug = f"civic2-{suf}", f"utilities-{suf}"
    _place_cleanup.extend([dept_slug, leaf_slug])
    with SessionLocal() as db:
        leaf = _seed_dept_leaf(db, dept_slug, leaf_slug, "Utilities")
        # Below the publish gate == genuinely empty now (gate is 1).
        for i in range(leaf_pages.LEAF_PAGE_MIN_PROVIDERS - 1):
            _add_place(db, leaf, f"Utility {i}")
        db.commit()
    r = client.get(f"/categories/{dept_slug}/{leaf_slug}")
    assert r.status_code == 404


# --- P7 leaf sub-grouping by neighborhood ------------------------------------


def _hood_card(name: str, hood: str) -> dict:
    return {"name": name, "neighborhood": hood}


def test_group_below_min_cards_stays_flat() -> None:
    cards = [_hood_card(f"b{i}", "Downtown" if i % 2 else "North Lake") for i in range(7)]
    assert _group_cards_by_neighborhood(cards) is None


def test_group_single_neighborhood_stays_flat() -> None:
    cards = [_hood_card(f"b{i}", "Downtown") for i in range(10)]
    assert _group_cards_by_neighborhood(cards) is None


def test_group_two_neighborhoods_sections_sorted_by_size() -> None:
    cards = [_hood_card(f"d{i}", "Downtown") for i in range(5)]
    cards += [_hood_card(f"n{i}", "North Lake") for i in range(3)]
    groups = _group_cards_by_neighborhood(cards)
    assert groups is not None
    assert [label for label, _ in groups] == ["Downtown", "North Lake"]  # largest first
    assert len(groups[0][1]) == 5 and len(groups[1][1]) == 3


def test_group_collapses_singletons_and_missing_into_catch_all() -> None:
    cards = [_hood_card(f"d{i}", "Downtown") for i in range(4)]
    cards += [_hood_card(f"n{i}", "North Lake") for i in range(3)]
    cards += [_hood_card("lonely", "Outpost")]  # one-off neighborhood
    cards += [_hood_card("nohood", "")]  # no district at all
    groups = _group_cards_by_neighborhood(cards)
    assert groups is not None
    labels = [label for label, _ in groups]
    assert labels[:2] == ["Downtown", "North Lake"]
    assert labels[-1] == "More across Lake Havasu City"
    assert {c["name"] for c in groups[-1][1]} == {"lonely", "nohood"}


def _add_provider_with_district(
    db: Session, leaf: Category, name: str, district: str
) -> None:
    ent = Entity(entity_type="commercial", slug=f"e-{uuid4().hex[:10]}", name=name,
                 source=_SOURCE)
    db.add(ent)
    db.flush()
    db.add(Provider(provider_name=name, category="x", slug=f"p-{uuid4().hex[:10]}",
                    is_active=True, draft=False, source=_SOURCE, entity_id=ent.id,
                    google_rating=4.6, google_review_count=30, district=district))
    db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))


def test_leaf_groups_by_neighborhood_when_spread(
    client: TestClient, _place_cleanup: list[str]
) -> None:
    """A leaf with 8 listings across 2 districts renders neighborhood sections."""
    suf = uuid4().hex[:6]
    dept_slug, leaf_slug = f"grp-{suf}", f"salons-{suf}"
    _place_cleanup.extend([dept_slug, leaf_slug])
    with SessionLocal() as db:
        leaf = _seed_dept_leaf(db, dept_slug, leaf_slug, "Salons")
        for i in range(4):
            _add_provider_with_district(db, leaf, f"Downtown Salon {i} {uuid4().hex[:4]}",
                                        "Downtown")
        for i in range(4):
            _add_provider_with_district(db, leaf, f"Lakeside Salon {i} {uuid4().hex[:4]}",
                                        "Lakeside")
        db.commit()
    r = client.get(f"/categories/{dept_slug}/{leaf_slug}")
    assert r.status_code == 200
    body = r.text
    assert 'class="also-sec"' in body  # lake neighborhood-section heading class
    assert ">Downtown</h2>" in body
    assert ">Lakeside</h2>" in body
    # Every listing landed in a named section -> no catch-all.
    assert "More across Lake Havasu City" not in body


def test_leaf_stays_flat_when_one_neighborhood(
    client: TestClient, _place_cleanup: list[str]
) -> None:
    """Eight listings all in one district keep the original flat grid."""
    suf = uuid4().hex[:6]
    dept_slug, leaf_slug = f"flat-{suf}", f"barbers-{suf}"
    _place_cleanup.extend([dept_slug, leaf_slug])
    with SessionLocal() as db:
        leaf = _seed_dept_leaf(db, dept_slug, leaf_slug, "Barbers")
        for i in range(8):
            _add_provider_with_district(db, leaf, f"Barber {i} {uuid4().hex[:4]}", "Downtown")
        db.commit()
    r = client.get(f"/categories/{dept_slug}/{leaf_slug}")
    assert r.status_code == 200
    assert 'class="biz-group-head"' not in r.text
