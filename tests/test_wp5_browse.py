"""WP-5 browse loop — pagination, filter-state honesty, chip generation, and
SQL-vs-Python parity for the flat-bucket listing machinery.

A.3 nav rewire (2026-06-09): the public ``/categories/{slug}`` flat pages are
retired (they 301 to taxonomy departments), so the route-level cases here
exercise the surviving public surface of this machinery — the
``/lake-havasu/{subcategory}`` SEO landings, which render the same
``_render_category_page`` pipeline pre-filtered to a subcategory.

Covers the packet's four required test classes:
  1. pagination params (``?page=`` honored over the 60-cap; window math)
  2. param-preservation matrix (every "All"/sort/filter link keeps other params)
  3. chip generation from seeded subtypes (present-only, count-ordered)
  4. SQL-filter parity (the SQL-only path matches the materialize path)

Providers auto-create their Entity on insert; each case inserts uniquely
suffixed rows and tears them down to stay isolated (mirrors test_hours_facets).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.categories import queries as cat_queries
from app.categories.queries import (
    CategoryFacets,
    category_listing,
    subcategory_chips_for_route,
)
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.main import app

_NOW = datetime(2026, 1, 5, 14, 0, 0, tzinfo=LAKE_HAVASU_TZ)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _seed_restaurants(n: int, *, subcategory: str = "restaurants", prefix: str = "WP5") -> list[str]:
    """Insert ``n`` active eat-drink providers; return their entity ids."""
    suf = uuid.uuid4().hex[:8]
    eids: list[str] = []
    with SessionLocal() as db:
        rows = []
        for i in range(n):
            p = Provider(
                provider_name=f"{prefix} {subcategory} {i:03d} {suf}",
                category="restaurant",
                subcategory=subcategory,
                google_primary_category="restaurant",
                google_rating=4.5,
                google_review_count=50 + i,
                verified=False,
                draft=False,
                is_active=True,
                pending_review=False,
                source="test-wp5",
                hours_structured={"monday": [{"open": "09:00", "close": "22:00"}]},
            )
            rows.append(p)
        db.add_all(rows)
        db.commit()
        eids = [p.entity_id for p in rows]
    return eids


def _cleanup(entity_ids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id.in_(entity_ids)))
        db.execute(delete(Entity).where(Entity.id.in_(entity_ids)))
        db.commit()


# ---------------------------------------------------------------------------
# 1. Pagination params
# ---------------------------------------------------------------------------


def test_page_two_returns_distinct_window_and_full_total() -> None:
    """``page=2`` returns the next slice; ``total`` stays the unpaged count."""
    eids = _seed_restaurants(7)
    try:
        with SessionLocal() as db:
            p1, total1 = category_listing(
                db, "eat-drink", now=_NOW, facets=CategoryFacets(sort="alpha"), limit=5, page=1
            )
            p2, total2 = category_listing(
                db, "eat-drink", now=_NOW, facets=CategoryFacets(sort="alpha"), limit=5, page=2
            )
        names1 = {c["name"] for c in p1}
        names2 = {c["name"] for c in p2}
        # Window sizes honor the per-page cap, not the legacy 60-card cap.
        assert len(p1) == 5
        assert 1 <= len(p2) <= 5
        # Totals reflect the whole match set on both pages (>= our 7 seeds).
        assert total1 == total2 >= 7
        # The two windows are disjoint (no card repeats across pages).
        assert names1.isdisjoint(names2)
    finally:
        _cleanup(eids)


def test_page_param_honored_over_default_card_limit() -> None:
    """A page beyond the first 60 is reachable (the 60-cap is per-page now)."""
    # Use a small per-page so we don't need 60+ seed rows to prove the point.
    eids = _seed_restaurants(3)
    try:
        with SessionLocal() as db:
            cards, total = category_listing(
                db, "eat-drink", now=_NOW, facets=CategoryFacets(sort="alpha"), limit=2, page=2
            )
        # With >=3 rows and per_page=2, page 2 is non-empty -> the param took.
        assert total >= 3
        assert len(cards) >= 1
    finally:
        _cleanup(eids)


def test_route_page_query_renders_pagination_controls(client: TestClient) -> None:
    """The page emits a 'Showing X-Y of N' line and rel=next when paged."""
    eids = _seed_restaurants(65)  # > one default page so a next link exists
    try:
        r = client.get("/lake-havasu/restaurants")
        assert r.status_code == 200
        body = r.text
        assert "Showing 1-" in body
        assert 'rel="next"' in body
    finally:
        _cleanup(eids)


# ---------------------------------------------------------------------------
# 2. Param-preservation matrix (DL-20)
# ---------------------------------------------------------------------------


def test_all_chip_preserves_other_params_and_drops_only_sub(client: TestClient) -> None:
    """The subtype 'All' chip keeps open/sort but clears the subcategory (the
    landing's subcategory lives in the path, so 'All' walks up to the bucket
    route URL)."""
    eids = _seed_restaurants(3, subcategory="restaurants")
    try:
        r = client.get("/lake-havasu/restaurants?open=1&sort=closest")
        assert r.status_code == 200
        body = r.text
        # The subtype "All" chip target preserves open + sort but drops sub. Its
        # exact markup carries data-filter="all" (HTML-escaped &).
        assert (
            'data-filter="all" href="/categories/eat-drink?open=1&amp;sort=closest"' in body
        )
    finally:
        _cleanup(eids)


def test_open_now_toggle_preserves_active_sort(client: TestClient) -> None:
    """Toggling Open now on a Closest-sorted page keeps the sort param."""
    r = client.get("/lake-havasu/restaurants?sort=closest")
    assert r.status_code == 200
    # The Open-now filter link carries the active sort forward.
    assert "open=1&amp;sort=closest" in r.text or "open=1&sort=closest" in r.text


def test_open_now_is_a_filter_not_a_sort_pill(client: TestClient) -> None:
    """DL-20: Open now lives in the filter row, never as a sort pill, and the
    sort row never shows two 'on' pills at once."""
    r = client.get("/lake-havasu/restaurants?open=1")
    body = r.text
    assert 'class="filterpill on"' in body
    # Exactly one sort pill is active (the default favorites), even with open=1.
    assert body.count('class="sortpill on"') == 1


def test_sort_explainer_matches_active_sort(client: TestClient) -> None:
    """Item 32: the explainer text reflects the active sort, not a static blurb."""
    r_default = client.get("/lake-havasu/restaurants")
    assert "shuffled fresh each day" in r_default.text  # the new default (Featured)
    r_fav = client.get("/lake-havasu/restaurants?sort=favorites")
    assert "weighted by review volume" in r_fav.text
    r_close = client.get("/lake-havasu/restaurants?sort=closest")
    assert "nearest to the Lake Havasu City civic center" in r_close.text
    assert "weighted by review volume" not in r_close.text


def test_active_filter_summary_line_renders_with_clear(client: TestClient) -> None:
    """C7: an active facet shows a summary line with a clear control."""
    eids = _seed_restaurants(3, subcategory="restaurants")
    try:
        r = client.get("/lake-havasu/restaurants")
        body = r.text
        assert "Restaurants" in body
        assert "clear" in body
        assert 'class="filtersummary"' in body
    finally:
        _cleanup(eids)


# ---------------------------------------------------------------------------
# 3. Chip generation from seeded subtypes (C8 / N-16)
# ---------------------------------------------------------------------------


def test_chips_generated_from_present_subtypes_ordered_by_count() -> None:
    """Only subtypes with live members render, ordered by descending count."""
    rest_eids = _seed_restaurants(5, subcategory="restaurants")
    bar_eids = _seed_restaurants(2, subcategory="bars-breweries")
    try:
        with SessionLocal() as db:
            chips = subcategory_chips_for_route(db, "eat-drink")
        by_slug = {c["slug"]: c for c in chips}
        # Both seeded subtypes appear; cafes-coffee / quick-bites do NOT (0 members
        # among our seeds — and any pre-existing fixtures only add, never remove).
        assert "restaurants" in by_slug
        assert "bars-breweries" in by_slug
        assert by_slug["restaurants"]["count"] >= 5
        assert by_slug["bars-breweries"]["count"] >= 2
        # Count-desc ordering: restaurants (>=5) precedes bars-breweries (>=2)
        # ONLY if restaurants truly outnumbers — assert relative order by count.
        order = [c["slug"] for c in chips]
        assert order.index("restaurants") < order.index("bars-breweries") or (
            by_slug["restaurants"]["count"] < by_slug["bars-breweries"]["count"]
        )
        # Every rendered chip has a positive count (zero-member chips omitted).
        assert all(c["count"] > 0 for c in chips)
    finally:
        _cleanup(rest_eids + bar_eids)


def test_tile_route_renders_no_chips() -> None:
    """Tile routes (no bucket) generate no chips -> template drops the row + the
    'Tap a type to narrow' copy (N-16)."""
    with SessionLocal() as db:
        assert subcategory_chips_for_route(db, "beauty-care") == []


def test_no_chip_route_omits_tap_to_narrow_copy(client: TestClient) -> None:
    # /lake-havasu/storage hosts on the services route; with no services
    # subtypes seeded there are no chips, so the narrowing copy must be absent.
    r = client.get("/lake-havasu/storage")
    assert r.status_code == 200
    assert "Tap a type to narrow" not in r.text


# ---------------------------------------------------------------------------
# 4. SQL-vs-Python parity
# ---------------------------------------------------------------------------


def test_sql_path_and_materialize_path_agree_on_membership() -> None:
    """The SQL-only listing (no scan facet) and the materialized listing
    (favorites sort forces a scan) return the SAME set of providers for the
    same route — only ordering/pagination differs, never membership."""
    eids = _seed_restaurants(6)
    seeded = set()
    with SessionLocal() as db:
        for e in eids:
            p = db.query(Provider).filter(Provider.entity_id == e).first()
            if p:
                seeded.add(p.provider_name)
    try:
        with SessionLocal() as db:
            # SQL-only path: alpha sort, no materialize.
            sql_cards, sql_total = category_listing(
                db, "eat-drink", now=_NOW, facets=CategoryFacets(sort="alpha"), limit=500
            )
            # Materialize path: favorites sort scans + sorts in Python.
            mat_cards, mat_total = category_listing(
                db, "eat-drink", now=_NOW, facets=CategoryFacets(sort="favorites"), limit=500
            )
        assert sql_total == mat_total
        sql_names = {c["name"] for c in sql_cards}
        mat_names = {c["name"] for c in mat_cards}
        # Both paths see every seeded provider, identically.
        assert seeded <= sql_names
        assert seeded <= mat_names
        assert sql_names == mat_names
    finally:
        _cleanup(eids)


def test_top_rated_predicate_runs_in_sql_without_materialize() -> None:
    """top_rated is a SQL predicate: it filters out a sub-4.0 row even on the
    non-materialized path (no Python scan needed)."""
    suf = uuid.uuid4().hex[:8]
    hi = f"WP5 HiRated {suf}"
    lo = f"WP5 LoRated {suf}"
    with SessionLocal() as db:
        hp = Provider(
            provider_name=hi, category="restaurant", subcategory="restaurants",
            google_rating=4.8, google_review_count=120, draft=False, is_active=True,
            pending_review=False, verified=False, source="test-wp5",
        )
        lp = Provider(
            provider_name=lo, category="restaurant", subcategory="restaurants",
            google_rating=3.1, google_review_count=120, draft=False, is_active=True,
            pending_review=False, verified=False, source="test-wp5",
        )
        db.add_all([hp, lp])
        db.commit()
        eids = [hp.entity_id, lp.entity_id]
    try:
        f = CategoryFacets(top_rated=True)
        assert f.needs_materialize is False  # proves the SQL-only path is taken
        with SessionLocal() as db:
            cards, _total = category_listing(db, "eat-drink", now=_NOW, facets=f, limit=500)
        names = {c["name"] for c in cards}
        assert hi in names
        assert lo not in names
    finally:
        _cleanup(eids)


# ---------------------------------------------------------------------------
# Card contract additions (D7 / D8 / DL-8 / DL-12)
# ---------------------------------------------------------------------------


def test_card_rating_hidden_below_three_reviews_dl12() -> None:
    """DL-12: a 2-review 5.0 renders no star (has_reviews False); a 3-review one does."""
    suf = uuid.uuid4().hex[:8]
    thin = f"WP5 Thin {suf}"
    ok = f"WP5 Credible {suf}"
    with SessionLocal() as db:
        tp = Provider(
            provider_name=thin, category="restaurant", subcategory="restaurants",
            google_rating=5.0, google_review_count=2, draft=False, is_active=True,
            pending_review=False, verified=False, source="test-wp5",
        )
        op = Provider(
            provider_name=ok, category="restaurant", subcategory="restaurants",
            google_rating=4.4, google_review_count=3, draft=False, is_active=True,
            pending_review=False, verified=False, source="test-wp5",
        )
        db.add_all([tp, op])
        db.commit()
        eids = [tp.entity_id, op.entity_id]
    try:
        with SessionLocal() as db:
            cards, _ = category_listing(db, "eat-drink", now=_NOW, facets=CategoryFacets(sort="alpha"), limit=500)
        by_name = {c["name"]: c for c in cards}
        assert by_name[thin]["has_reviews"] is False
        assert by_name[thin]["rating"] is None
        assert by_name[ok]["has_reviews"] is True
        assert by_name[ok]["rating"] == "4.4"
    finally:
        _cleanup(eids)


def test_out_of_area_card_carries_distance_hint_dl8() -> None:
    """DL-8: a far-flung listing keeps its place but gains a distance hint."""
    suf = uuid.uuid4().hex[:8]
    near = f"WP5 InTown {suf}"
    far = f"WP5 Parker {suf}"
    with SessionLocal() as db:
        np = Provider(
            provider_name=near, category="restaurant", subcategory="restaurants",
            lat=cat_queries._REF_LAT, lng=cat_queries._REF_LNG,
            draft=False, is_active=True, pending_review=False, verified=False, source="test-wp5",
        )
        fp = Provider(
            provider_name=far, category="restaurant", subcategory="restaurants",
            lat=34.15, lng=-114.28,  # ~Parker area, well past the out-of-area km
            draft=False, is_active=True, pending_review=False, verified=False, source="test-wp5",
        )
        db.add_all([np, fp])
        db.commit()
        eids = [np.entity_id, fp.entity_id]
    try:
        with SessionLocal() as db:
            cards, _ = category_listing(db, "eat-drink", now=_NOW, facets=CategoryFacets(sort="alpha"), limit=500)
        by_name = {c["name"]: c for c in cards}
        assert by_name[near]["distance_hint"] == ""
        assert "Parker area" in by_name[far]["distance_hint"]
        # The far one is still present (not hidden).
        assert far in by_name
    finally:
        _cleanup(eids)


def test_mis_geocoded_card_gets_no_fabricated_distance_hint() -> None:
    """A row whose coords sit far outside the region (mis-geocode) shows no hint,
    not a fabricated "~2405 min away . Parker area" line (prod-smoke bug)."""
    suf = uuid.uuid4().hex[:8]
    name = f"WP5 BadGeo {suf}"
    with SessionLocal() as db:
        # ~1700+ km from the LHC anchor (well past _FAR_OUT_OF_REGION_KM).
        p = Provider(
            provider_name=name, category="restaurant", subcategory="restaurants",
            lat=45.0, lng=-104.0,
            draft=False, is_active=True, pending_review=False, verified=False, source="test-wp5",
        )
        db.add(p)
        db.commit()
        eids = [p.entity_id]
    try:
        with SessionLocal() as db:
            cards, _ = category_listing(db, "eat-drink", now=_NOW, facets=CategoryFacets(sort="alpha"), limit=500)
        by_name = {c["name"]: c for c in cards}
        assert name in by_name  # still rendered, not hidden
        assert by_name[name]["distance_hint"] == ""  # but no fabricated distance
    finally:
        _cleanup(eids)
