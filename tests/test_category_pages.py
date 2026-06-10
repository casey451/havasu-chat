"""Direction C category-page tests (PR D5; A.3 nav rewire 2026-06-09).

Coverage:

1. ``CATEGORY_FILTERS`` / ``CATEGORY_DISPLAY`` / ``_TAB_FOR_ROUTE``
   module-level invariants -- the flat-bucket machinery is retired from
   public ``/categories/{slug}`` rendering but still backs the
   ``/lake-havasu/{subcategory}`` landings, so its internal consistency
   still matters.
2. ``is_valid_category_slug()`` -- known slugs, unknown slugs, edge
   cases (empty, whitespace, casing).
3. ``category_count()`` / ``category_cards()`` contracts -- None DB,
   exception swallowing, slug filtering, no-zero rule.
4. End-to-end ``GET /categories/{slug}`` (A.3 rewire):
   - every retired flat slug 301s to its taxonomy department
     (``ROUTE_SLUG_ALIASES``); nothing renders the old lumped pages.
   - master-bucket slugs 301 in ONE hop (chains collapsed through the
     alias map).
   - ``on-the-water`` / ``pets`` -- slugs shared with the new tree --
     render the department landing when the taxonomy is present.
   - 404 for an unknown slug.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.categories import queries as cat_queries
from app.categories.router import ROUTE_SLUG_ALIASES
from app.db.database import SessionLocal
from app.home.queries import LEGACY_PROVIDER_CATEGORY_LABELS
from app.main import app
from app.v1.categories import MASTER_BUCKETS

# ---------------------------------------------------------------------------
# Module-level invariants
# ---------------------------------------------------------------------------


def test_category_filters_keys_match_display_keys() -> None:
    """Every route in CATEGORY_FILTERS must have display copy and a
    tab mapping. Missing entries would render an empty page header or
    fall back to the wrong tab."""
    filter_keys = set(cat_queries.CATEGORY_FILTERS.keys())
    display_keys = set(cat_queries.CATEGORY_DISPLAY.keys())
    tab_keys = set(cat_queries._TAB_FOR_ROUTE.keys())
    assert filter_keys == display_keys, (
        f"CATEGORY_FILTERS and CATEGORY_DISPLAY drift: "
        f"only-in-filters={filter_keys - display_keys}, "
        f"only-in-display={display_keys - filter_keys}"
    )
    assert filter_keys == tab_keys, (
        f"CATEGORY_FILTERS and _TAB_FOR_ROUTE drift: "
        f"only-in-filters={filter_keys - tab_keys}, "
        f"only-in-tabs={tab_keys - filter_keys}"
    )


def test_category_filters_has_expected_route_count() -> None:
    """15 unique routes: 4 mega-tabs + 12 D4 tile routes - 1 shared
    (on-the-water appears in both lists)."""
    assert len(cat_queries.CATEGORY_FILTERS) == 15


def test_every_filter_tuple_is_nonempty_and_unique() -> None:
    """A filter tuple with zero slugs would render an empty grid every
    time. Duplicate slugs within a tuple are a bug."""
    for route, slugs in cat_queries.CATEGORY_FILTERS.items():
        assert isinstance(slugs, tuple), f"{route} filter is not a tuple"
        assert len(slugs) > 0, f"{route} has empty filter tuple"
        assert len(set(slugs)) == len(slugs), f"{route} has duplicate slugs in filter: {slugs}"


def test_every_filter_slug_is_known_legacy_category() -> None:
    """Every legacy slug in CATEGORY_FILTERS must appear in
    LEGACY_PROVIDER_CATEGORY_LABELS -- a typo here means a category
    page would silently surface 0 providers forever."""
    for route, slugs in cat_queries.CATEGORY_FILTERS.items():
        for slug in slugs:
            assert slug in LEGACY_PROVIDER_CATEGORY_LABELS, (
                f"route {route} filter slug {slug!r} not in LEGACY_PROVIDER_CATEGORY_LABELS"
            )


def test_every_display_entry_is_label_plus_one_liner() -> None:
    """CATEGORY_DISPLAY values are (label, one_liner) tuples. Missing
    one_liner would render a blank sub line; missing label would render
    a blank header."""
    for route, value in cat_queries.CATEGORY_DISPLAY.items():
        assert isinstance(value, tuple), f"{route} display is not a tuple"
        assert len(value) == 2, f"{route} display tuple is wrong arity"
        label, one_liner = value
        assert isinstance(label, str) and label.strip(), f"{route} display label is empty"
        assert isinstance(one_liner, str) and one_liner.strip(), (
            f"{route} display one_liner is empty"
        )


def test_active_tab_for_returns_known_tab() -> None:
    """Every route maps to one of the five known tab slugs (the four
    mega-tabs plus 'today' as a defensive fallback)."""
    known_tabs = {"today", "eat-drink", "on-the-water", "things-to-do", "services"}
    for route in cat_queries.CATEGORY_FILTERS:
        tab = cat_queries.active_tab_for(route)
        assert tab in known_tabs, f"route {route} maps to unknown tab {tab!r}"


def test_active_tab_for_unknown_slug_defaults_to_today() -> None:
    """Defensive fallback so the template doesn't crash on a malformed
    or new route added to the router but not the tab map."""
    assert cat_queries.active_tab_for("garbage") == "today"
    assert cat_queries.active_tab_for("") == "today"


# ---------------------------------------------------------------------------
# is_valid_category_slug
# ---------------------------------------------------------------------------


def test_is_valid_category_slug_known() -> None:
    for slug in ("eat-drink", "services", "pets", "lodging-vacation-rentals"):
        assert cat_queries.is_valid_category_slug(slug) is True


def test_is_valid_category_slug_unknown() -> None:
    assert cat_queries.is_valid_category_slug("garbage") is False
    assert cat_queries.is_valid_category_slug("") is False
    assert cat_queries.is_valid_category_slug("/eat-drink/") is False


def test_is_valid_category_slug_case_insensitive_and_trimmed() -> None:
    """URL routing is case-sensitive, but the validator trims and
    lowercases so error paths don't depend on exact casing."""
    assert cat_queries.is_valid_category_slug("EAT-DRINK") is True
    assert cat_queries.is_valid_category_slug("  pets  ") is True


# ---------------------------------------------------------------------------
# category_count / category_cards with None DB and exceptions
# ---------------------------------------------------------------------------


def test_category_count_returns_none_for_none_db() -> None:
    assert cat_queries.category_count(None, "eat-drink") is None


def test_category_count_returns_none_for_unknown_slug() -> None:
    """An unknown slug returns None (not raising) -- the router does
    the 404; this layer must not blow up if called with a bad slug."""
    assert cat_queries.category_count(None, "garbage") is None


def test_category_count_swallows_db_exception() -> None:
    """A DB hiccup must not 500 the page -- count returns None and the
    template hides the count clause."""

    class _BrokenSession:
        def query(self, *_a, **_kw):
            raise RuntimeError("connection lost")

    assert cat_queries.category_count(_BrokenSession(), "eat-drink") is None


def test_category_count_returns_none_when_query_returns_zero() -> None:
    """No-zero rule at the query layer: 0 collapses to None so the
    template ``{% if category_count %}`` clause hides cleanly."""

    class _ZeroQuery:
        def filter(self, *_a, **_kw):
            return self

        def scalar(self):
            return 0

    class _ZeroSession:
        def query(self, *_a, **_kw):
            return _ZeroQuery()

    assert cat_queries.category_count(_ZeroSession(), "eat-drink") is None


def test_category_count_returns_int_when_query_returns_positive() -> None:
    class _CountQuery:
        def filter(self, *_a, **_kw):
            return self

        def scalar(self):
            return 42

    class _CountSession:
        def query(self, *_a, **_kw):
            return _CountQuery()

    assert cat_queries.category_count(_CountSession(), "eat-drink") == 42


def test_category_cards_returns_empty_for_none_db() -> None:
    assert cat_queries.category_cards(None, "eat-drink", now=datetime.now()) == []


def test_category_cards_returns_empty_for_unknown_slug() -> None:
    """Unknown slug returns []. The router will already have 404'd by
    the time anyone calls this with a bad slug, but defensive is cheap."""
    assert cat_queries.category_cards(None, "garbage", now=datetime.now()) == []


def test_category_cards_swallows_db_exception() -> None:
    """A DB hiccup must not 500 the page."""

    class _BrokenQuery:
        def filter(self, *_a, **_kw):
            return self

        def order_by(self, *_a, **_kw):
            return self

        def limit(self, *_a, **_kw):
            return self

        def all(self):
            raise RuntimeError("connection lost")

    class _BrokenSession:
        def query(self, *_a, **_kw):
            return _BrokenQuery()

    cards = cat_queries.category_cards(_BrokenSession(), "eat-drink", now=datetime.now())
    assert cards == []


# ---------------------------------------------------------------------------
# End-to-end via TestClient (A.3 nav rewire: redirects + department render)
# ---------------------------------------------------------------------------

_SOURCE = "test-category-pages"


def test_category_route_404_for_unknown_slug() -> None:
    client = TestClient(app)
    resp = client.get("/categories/garbage-slug")
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "slug",
    sorted(set(cat_queries.CATEGORY_FILTERS) - {"on-the-water", "pets"}),
)
def test_retired_flat_slug_301s_to_department(slug: str) -> None:
    """Every retired flat route 301s to its taxonomy department — the old
    lumped pages never render."""
    client = TestClient(app, follow_redirects=False)
    resp = client.get(f"/categories/{slug}")
    assert resp.status_code == 301, f"/categories/{slug} should 301, got {resp.status_code}"
    assert resp.headers["location"] == ROUTE_SLUG_ALIASES[slug]


def test_services_grab_bag_301s_to_categories_index() -> None:
    """The old SERVICES mega-bucket has no single department successor; it
    301s to the /categories index, which lists all of them."""
    client = TestClient(app, follow_redirects=False)
    resp = client.get("/categories/services")
    assert resp.status_code == 301
    assert resp.headers["location"] == "/categories"
    final = client.get("/categories/services", follow_redirects=True)
    assert final.status_code == 200


def test_redirect_preserves_query_string() -> None:
    client = TestClient(app, follow_redirects=False)
    resp = client.get("/categories/eat-drink?open=1")
    assert resp.status_code == 301
    assert resp.headers["location"] == "/categories/eat-and-drink?open=1"


@pytest.mark.parametrize("bucket", [b["slug"] for b in MASTER_BUCKETS])
def test_master_bucket_slug_301s_in_one_hop(bucket: str) -> None:
    """Browse Havasu bucket links 301 straight to a live destination — the
    chain through the retired flat slug is collapsed server-side, so the
    location header is never itself a redirecting flat route."""
    client = TestClient(app, follow_redirects=False)
    resp = client.get(f"/categories/{bucket}")
    assert resp.status_code == 301, f"/categories/{bucket} should 301, got {resp.status_code}"
    dest = resp.headers["location"]
    # Never a retired flat slug (which would force a second hop).
    tail = dest.rsplit("/", 1)[-1]
    assert tail not in ROUTE_SLUG_ALIASES, f"{bucket} redirects to retired slug {dest}"


def test_food_drink_and_events_bucket_redirect_destinations() -> None:
    """Regression: Browse Havasu links land on the taxonomy departments."""
    client = TestClient(app, follow_redirects=False)
    cases = {
        "food-drink": "/categories/eat-and-drink",
        "events": "/categories/things-to-do-and-attractions",
        "sports-fitness": "/categories/fitness-and-wellness",
        "stay": "/categories/lodging",
        "shopping": "/categories/shopping-and-retail",
    }
    for bucket, dest in cases.items():
        resp = client.get(f"/categories/{bucket}")
        assert resp.status_code == 301
        assert resp.headers["location"] == dest


def test_shared_slug_renders_department_when_taxonomy_present() -> None:
    """``pets`` is both a retired flat slug and a department slug — with the
    taxonomy seeded, /categories/pets renders the department landing (leaf
    grid), NOT the old lumped list and NOT a redirect."""
    from app.categories import leaf_pages
    from app.db.models import Category, Entity, EntityCategory, Provider

    gate = leaf_pages.LEAF_PAGE_MIN_PROVIDERS
    suf = uuid4().hex[:6]
    leaf_slug = f"pets-leaf-{suf}"
    created_dept = False
    with SessionLocal() as db:
        # The directory_v1 migration seeds a childless level-0 'pets' row;
        # attach the leaf to it when present (prod's A.3 seed did the same).
        dept = db.scalars(
            select(Category).where(Category.slug == "pets", Category.level == 0)
        ).first()
        if dept is None:
            dept = Category(slug="pets", name="Pets", sort_order=7, level=0)
            db.add(dept)
            db.flush()
            created_dept = True
        leaf = Category(
            slug=leaf_slug, name="Groomers", sort_order=0, level=1, parent_id=dept.id
        )
        db.add(leaf)
        db.flush()
        for i in range(gate):
            ent = Entity(
                entity_type="commercial",
                slug=f"cp-ent-{uuid4().hex[:10]}",
                name=f"Groomer {i}",
                source=_SOURCE,
            )
            db.add(ent)
            db.flush()
            db.add(
                Provider(
                    provider_name=f"Groomer {i}",
                    category="x",
                    slug=f"cp-prov-{uuid4().hex[:10]}",
                    is_active=True,
                    draft=False,
                    source=_SOURCE,
                    entity_id=ent.id,
                )
            )
            db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
        db.commit()
    try:
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/categories/pets")
        assert resp.status_code == 200
        body = resp.text
        assert f'href="/categories/pets/{leaf_slug}"' in body
        assert "Groomers" in body
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
            cleanup_slugs = [leaf_slug] + (["pets"] if created_dept else [])
            for cat in db.scalars(
                select(Category).where(Category.slug.in_(cleanup_slugs))
            ).all():
                db.delete(cat)
            db.commit()


def test_home_redesign_tabs_are_real_anchors() -> None:
    """Home includes category navigation anchors."""
    client = TestClient(app)
    resp = client.get("/home")
    assert resp.status_code == 200
    body = resp.text
    assert 'href="/categories"' in body
    assert "Explore" in body
