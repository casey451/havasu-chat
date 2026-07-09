"""WS9a — server-rendered cuisine facet on Eat & Drink leaf pages.

Two layers:

* ``_leaf_cuisine_facet`` — the pure chip/href builder (no DB): only Eat & Drink
  leaves get a chip row, only cuisines with >= _CUISINE_CHIP_MIN listings become
  chips, chip hrefs preserve the active sort/open toggle, the active chip carries
  its label + count for the filter summary.
* the route — ``/categories/eat-and-drink/{leaf}?cuisine=mexican`` renders ONLY
  the matching cuisine, server-side, with a live chip row; a non-Eat-&-Drink leaf
  renders no cuisine row at all.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.categories import router as cat_router
from app.categories.leaf_pages import Leaf
from app.categories.router import _leaf_cuisine_facet
from app.db.database import SessionLocal
from app.db.models import Category, Entity, EntityCategory, Provider

BASE = "/categories/eat-and-drink/restaurants"

_EAT_LEAF = Leaf(
    id=1,
    slug="restaurants",
    name="Restaurants",
    department_slug="eat-and-drink",
    department_name="Eat & Drink",
)


def _cuisine_cards(spec: dict[str, int]) -> list[dict]:
    """Cards carrying a derived ``cuisine`` token, ``count`` per cuisine slug."""
    cards: list[dict] = []
    for slug, n in spec.items():
        for i in range(n):
            cards.append({"name": f"{slug}-{i}", "cuisine": slug, "is_open": True})
    return cards


# --- _leaf_cuisine_facet (pure) --------------------------------------------


def test_facet_none_for_non_eat_drink_leaf() -> None:
    leaf = Leaf(id=2, slug="plumbing", name="Plumbing",
                department_slug="home-and-property-services",
                department_name="Home & Property Services")
    cards = _cuisine_cards({"mexican": 3, "italian": 3})
    assert _leaf_cuisine_facet({}, leaf, cards, base_path="/x") is None


def test_facet_none_when_fewer_than_two_cuisines_present() -> None:
    # Only one cuisine clears the chip minimum -> no chip row (honest facets).
    cards = _cuisine_cards({"mexican": 5}) + [{"name": "p", "cuisine": "", "is_open": None}]
    assert _leaf_cuisine_facet({}, _EAT_LEAF, cards, base_path=BASE) is None


def test_facet_chips_in_canonical_order_with_counts() -> None:
    cards = _cuisine_cards({"italian": 2, "mexican": 3})
    facet = _leaf_cuisine_facet({}, _EAT_LEAF, cards, base_path=BASE)
    assert facet is not None
    # Canonical cuisine order puts Mexican before Italian regardless of input order.
    assert [(c["slug"], c["count"]) for c in facet["chips"]] == [
        ("mexican", 3),
        ("italian", 2),
    ]
    assert facet["all_active"] is True
    assert facet["active"] is None
    assert facet["all_href"] == BASE
    assert facet["chips"][0]["href"] == f"{BASE}?cuisine=mexican"


def test_facet_below_min_cuisine_is_dropped() -> None:
    # italian has only 1 -> below _CUISINE_CHIP_MIN (2); with just mexican left
    # there are fewer than two chips, so the whole row is suppressed.
    cards = _cuisine_cards({"mexican": 4, "italian": 1})
    assert _leaf_cuisine_facet({}, _EAT_LEAF, cards, base_path=BASE) is None


def test_facet_active_cuisine_marked_and_summarized() -> None:
    cards = _cuisine_cards({"mexican": 3, "italian": 2})
    facet = _leaf_cuisine_facet({"cuisine": "mexican"}, _EAT_LEAF, cards, base_path=BASE)
    assert facet is not None
    assert facet["active"] == "mexican"
    assert facet["active_label"] == "Mexican"
    assert facet["active_count"] == 3
    assert facet["all_active"] is False
    mex = next(c for c in facet["chips"] if c["slug"] == "mexican")
    assert mex["active"] is True


def test_facet_chip_hrefs_preserve_sort_and_open() -> None:
    cards = _cuisine_cards({"mexican": 3, "italian": 2})
    facet = _leaf_cuisine_facet(
        {"sort": "favorites", "open": "1"}, _EAT_LEAF, cards, base_path=BASE
    )
    assert facet is not None
    mex = next(c for c in facet["chips"] if c["slug"] == "mexican")
    assert mex["href"] == f"{BASE}?cuisine=mexican&sort=favorites&open=1"
    # The "All" chip clears cuisine but keeps sort/open.
    assert facet["all_href"] == f"{BASE}?sort=favorites&open=1"


def test_facet_ignores_unknown_cuisine_param() -> None:
    cards = _cuisine_cards({"mexican": 3, "italian": 2})
    facet = _leaf_cuisine_facet({"cuisine": "klingon"}, _EAT_LEAF, cards, base_path=BASE)
    assert facet is not None
    assert facet["active"] is None
    assert facet["all_active"] is True


# --- route integration ------------------------------------------------------


@pytest.fixture
def eat_leaf() -> Iterator[dict]:
    """An Eat & Drink leaf with 3 Mexican + 2 Italian + 1 no-cuisine providers.

    Reuses the real ``eat-and-drink`` department (created by a migration seed on
    some DBs) so the facet's department gate fires, and attaches a uniquely
    slugged leaf so it never collides with a real ``restaurants`` leaf.
    """
    suf = uuid4().hex[:6]
    source = f"test-ws9a-{suf}"
    leaf_slug = f"ws9a-restaurants-{suf}"
    created_cat_ids: list[int] = []
    seeds = (
        ("mexican_restaurant", "mexican", 3),
        ("italian_restaurant", "italian", 2),
        ("cafe", None, 1),
    )
    names: dict[str, list[str]] = {"mexican": [], "italian": [], "none": []}
    with SessionLocal() as db:
        dept = db.scalars(
            select(Category).where(Category.slug == "eat-and-drink", Category.level == 0)
        ).first()
        if dept is None:
            dept = Category(slug="eat-and-drink", name="Eat & Drink", sort_order=0, level=0)
            db.add(dept)
            db.flush()
            created_cat_ids.append(dept.id)
        leaf = Category(slug=leaf_slug, name="Restaurants", sort_order=0, level=1,
                        parent_id=dept.id)
        db.add(leaf)
        db.flush()
        created_cat_ids.append(leaf.id)
        for gtype, cuisine, n in seeds:
            for i in range(n):
                nm = f"WS9A {cuisine or 'plain'} {i} {suf}"
                ent = Entity(entity_type="commercial", slug=f"ws9a-ent-{uuid4().hex[:10]}",
                             name=nm, source=source)
                db.add(ent)
                db.flush()
                db.add(Provider(
                    provider_name=nm, category="food_drink",
                    slug=f"ws9a-prov-{uuid4().hex[:10]}", is_active=True, draft=False,
                    source=source, entity_id=ent.id, google_primary_category=gtype,
                    google_categories=[gtype], google_rating=4.5, google_review_count=40,
                ))
                db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
                names[cuisine or "none"].append(nm)
        db.commit()
    cat_router.reset_index_cache()
    try:
        yield {"leaf_slug": leaf_slug, "names": names, "source": source}
    finally:
        with SessionLocal() as db:
            for prov in db.scalars(select(Provider).where(Provider.source == source)).all():
                db.delete(prov)
            for ent in db.scalars(select(Entity).where(Entity.source == source)).all():
                for ec in db.scalars(
                    select(EntityCategory).where(EntityCategory.entity_id == ent.id)
                ).all():
                    db.delete(ec)
                db.delete(ent)
            if created_cat_ids:
                for cat in db.scalars(
                    select(Category).where(Category.id.in_(created_cat_ids))
                ).all():
                    db.delete(cat)
            db.commit()
        cat_router.reset_index_cache()


def test_leaf_renders_cuisine_chip_row(client, eat_leaf: dict) -> None:
    r = client.get(f"/categories/eat-and-drink/{eat_leaf['leaf_slug']}")
    assert r.status_code == 200
    body = r.text
    assert 'aria-label="Filter by cuisine"' in body
    # Chips for both present cuisines, with live counts.
    assert "Mexican" in body and "Italian" in body
    assert "?cuisine=mexican" in body


def test_cuisine_param_returns_only_that_cuisine(client, eat_leaf: dict) -> None:
    import re

    r = client.get(f"/categories/eat-and-drink/{eat_leaf['leaf_slug']}?cuisine=mexican")
    assert r.status_code == 200
    # The visible listing is Mexican-only. The ItemList JSON-LD legitimately still
    # enumerates the whole canonical leaf (facet views canonical → the bare page),
    # so strip the ld+json blocks before asserting on the rendered cards.
    visible = re.sub(
        r'<script type="application/ld\+json">.*?</script>', "", r.text, flags=re.DOTALL
    )
    for nm in eat_leaf["names"]["mexican"]:
        assert nm in visible
    for nm in eat_leaf["names"]["italian"]:
        assert nm not in visible
    for nm in eat_leaf["names"]["none"]:
        assert nm not in visible
    # Honest active-filter summary + active chip.
    assert "Filtered to" in visible
    assert 'aria-current="true"' in visible


def test_non_eat_drink_leaf_has_no_cuisine_row(client, seeded_nav_departments: dict) -> None:
    # The nav fixture seeds a home-and-property-services leaf; it must not carry a
    # cuisine facet even though its cards have a (blank) cuisine token.
    from app.db.database import SessionLocal
    from app.db.models import Category

    with SessionLocal() as db:
        leaf = db.scalars(
            select(Category).where(
                Category.level == 1,
                Category.slug.like("nav-leaf-home-and-property-services-%"),
            )
        ).first()
        assert leaf is not None
        slug = leaf.slug
    r = client.get(f"/categories/home-and-property-services/{slug}")
    assert r.status_code == 200
    assert 'aria-label="Filter by cuisine"' not in r.text
