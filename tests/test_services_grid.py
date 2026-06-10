"""Direction C Service icon grid tests (PR D4).

Coverage:

1. ``_SERVICE_TILES`` module-level invariants (tile count, key shape,
   route validity against CATEGORY_FILTERS, slug validity against
   LEGACY_PROVIDER_CATEGORY_LABELS, no double-count with the eat row,
   no duplicate routes).
2. ``queries_c.services_grid()`` contract:
   - 12 cards always, ordered to match the constant.
   - DB None / DB error swallow into "all counts None".
   - Mocked DB rows map correctly to per-tile counts -- each tile's
     count is the SUM of all CATEGORY_FILTERS[route] slugs, matching
     the slim-header count on /categories/{route}.
   - No-zero rule: count 0 collapses to None + empty count_label.
3. End-to-end render via ``GET /home?redesign=1``:
   - Services section present.
   - All 12 tile names appear in the rendered HTML.
   - No "0 listed" copy anywhere.
   - href routes to /categories/{route}.

The grid surface is deterministic against the constant tuple, so most
tests run without a real DB. One end-to-end test exercises the
TestClient render path.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.categories.queries import CATEGORY_FILTERS
from app.home import queries_c
from app.home.queries import LEGACY_PROVIDER_CATEGORY_LABELS
from app.main import app

# ---------------------------------------------------------------------------
# Module-level constant invariants
# ---------------------------------------------------------------------------


def test_service_tiles_is_a_tuple_of_dicts() -> None:
    """``_SERVICE_TILES`` must be an immutable tuple so mutation in a
    downstream module can't reshape the grid at runtime."""
    assert isinstance(queries_c._SERVICE_TILES, tuple)
    for tile in queries_c._SERVICE_TILES:
        assert isinstance(tile, dict)


def test_service_tiles_has_twelve_entries() -> None:
    """The grid is 6 columns x 2 rows = 12 tiles. Adding a 13th tile
    requires a CSS layout change (3-row grid or hidden cell)."""
    assert len(queries_c._SERVICE_TILES) == 12


def test_every_tile_has_required_keys() -> None:
    """The template reads name/route/svg_path on every tile.
    A missing key would render a blank or KeyError in Jinja."""
    required = {"name", "route", "svg_path"}
    for tile in queries_c._SERVICE_TILES:
        missing = required - set(tile.keys())
        assert not missing, f"tile {tile.get('name', tile)} missing keys {missing}"


def test_every_tile_has_nonempty_string_values() -> None:
    """No tile may have an empty string for any required field."""
    for tile in queries_c._SERVICE_TILES:
        for key in ("name", "route", "svg_path"):
            value = tile[key]
            assert isinstance(value, str) and value, (
                f"tile {tile.get('name')} key {key} must be non-empty string"
            )


def test_every_tile_route_is_in_category_filters() -> None:
    """Each tile's route must map to an entry in CATEGORY_FILTERS so
    ``services_grid()`` can resolve the legacy slug set used to count
    providers. A tile pointing at an unknown route would silently
    count 0 forever -- and clicking the tile would 404 on the
    destination page. The two constants drift in lockstep."""
    for tile in queries_c._SERVICE_TILES:
        route = tile["route"]
        assert route in CATEGORY_FILTERS, (
            f"tile {tile['name']} route {route!r} not in CATEGORY_FILTERS "
            "(see app/categories/queries.py)"
        )


def test_every_tile_filter_slug_is_in_legacy_category_labels() -> None:
    """Every legacy ``Provider.category`` slug surfaced through any
    tile's ``CATEGORY_FILTERS[route]`` tuple must be a known taxonomy
    value. Drift here means a tile undercounts (silently) when an
    unknown slug doesn't match any rows. Also test-redundant with
    ``test_category_pages`` but kept here so the failure points at
    _SERVICE_TILES when that's what got edited."""
    for tile in queries_c._SERVICE_TILES:
        for slug in CATEGORY_FILTERS[tile["route"]]:
            assert slug in LEGACY_PROVIDER_CATEGORY_LABELS, (
                f"tile {tile['name']} route {tile['route']!r} includes "
                f"slug {slug!r} which is not in LEGACY_PROVIDER_CATEGORY_LABELS"
            )


def test_no_tile_filter_slug_overlaps_the_eat_row() -> None:
    """The eat row already counts food/drink Providers. A services
    tile whose CATEGORY_FILTERS tuple includes a food/drink slug would
    double-count and visually overlap the two surfaces. Detect at the
    constant level."""
    food_drink_slugs = set(queries_c._FOOD_DRINK_CATEGORIES)
    service_slugs: set[str] = set()
    for tile in queries_c._SERVICE_TILES:
        service_slugs.update(CATEGORY_FILTERS[tile["route"]])
    overlap = service_slugs & food_drink_slugs
    assert not overlap, f"service tiles overlap eat row: {overlap}"


def test_tile_names_are_unique() -> None:
    """Two tiles with the same display name would confuse navigation
    and a11y. Detect at the constant level."""
    names = [tile["name"] for tile in queries_c._SERVICE_TILES]
    assert len(set(names)) == len(names), f"duplicate tile names: {names}"


def test_tile_routes_are_unique() -> None:
    """Two tiles pointing at the same /categories/{route} are an
    editorial error -- pick one. This is the new tile-identity check
    after dropping the per-tile ``slug`` field; routes are now both
    the tap target AND the count-resolution key."""
    routes = [tile["route"] for tile in queries_c._SERVICE_TILES]
    assert len(set(routes)) == len(routes), f"duplicate tile routes: {routes}"


def test_tile_svg_paths_look_like_svg_path_data() -> None:
    """Inline SVG paths must start with a valid SVG command (M, m, L, l,
    A, a, etc.). A malformed path renders an invisible tile -- worse
    than a missing icon."""
    valid_starts = set("MmLlHhVvCcSsQqTtAaZz")
    for tile in queries_c._SERVICE_TILES:
        first = tile["svg_path"].lstrip()[:1]
        assert first in valid_starts, (
            f"tile {tile['name']} svg_path must start with SVG command, got {first!r}"
        )


# ---------------------------------------------------------------------------
# services_grid() contract
# ---------------------------------------------------------------------------


def test_services_grid_returns_twelve_cards_with_none_db() -> None:
    """A test or DB outage that calls with ``db=None`` must not 500;
    the grid still renders with all counts as None."""
    cards = queries_c.services_grid(None)
    assert len(cards) == 12
    for card in cards:
        assert card["count"] is None
        assert card["count_label"] == ""


def test_services_grid_card_shape() -> None:
    """Every card has the keys the template reads. None-DB path is
    sufficient for shape verification (counts always None there)."""
    cards = queries_c.services_grid(None)
    expected_keys = {"name", "route", "svg_path", "count", "count_label", "href"}
    for card in cards:
        missing = expected_keys - set(card.keys())
        assert not missing, f"card {card.get('name')} missing keys {missing}"


def test_services_grid_card_href_routes_to_categories() -> None:
    """Tile hrefs must point at ``/categories/{route}`` -- D5 will
    create those pages. Any deviation breaks future routing."""
    cards = queries_c.services_grid(None)
    for card in cards:
        assert card["href"] == f"/categories/{card['route']}"


def test_services_grid_tile_count_reconciles_with_category_page() -> None:
    """S4 — a /home service tile count must equal the slim-header count on
    ``/categories/{route}``. Both now compute via the same
    ``route_provider_filter`` (subcategory-primary), so seeding real providers
    and comparing the two surfaces proves no drift."""
    import uuid
    from datetime import datetime

    from sqlalchemy import delete

    from app.categories.queries import CategoryFacets, category_count, category_listing
    from app.core.timezone import LAKE_HAVASU_TZ
    from app.db.database import SessionLocal
    from app.db.models import Entity, Provider

    suf = uuid.uuid4().hex[:8]
    now = datetime(2026, 1, 5, 14, 0, 0, tzinfo=LAKE_HAVASU_TZ)
    # Three health providers (subcategory-classified) -> health-wellness-care tile.
    with SessionLocal() as db:
        made = [
            Provider(
                provider_name=f"Clinic {i} {suf}",
                category="retail",  # deliberately WRONG legacy -> proves pivot
                subcategory="health-medical",
                verified=False,
                draft=False,
                is_active=True,
                pending_review=False,
                source="test-s4",
            )
            for i in range(3)
        ]
        for p in made:
            db.add(p)
        db.commit()
        eids = [p.entity_id for p in made]

    try:
        with SessionLocal() as db:
            cards = queries_c.services_grid(db)
            by_route = {c["route"]: c for c in cards}
            tile_count = by_route["health-wellness-care"]["count"]
            page_count = category_count(db, "health-wellness-care")
            listing, listing_total = category_listing(
                db, "health-wellness-care", now=now, facets=CategoryFacets()
            )
        # The home tile, the page header count, and the listing total all agree.
        assert tile_count == page_count == listing_total
        assert tile_count >= 3
    finally:
        with SessionLocal() as db:
            db.execute(delete(Provider).where(Provider.entity_id.in_(eids)))
            db.execute(delete(Entity).where(Entity.id.in_(eids)))
            db.commit()


def test_services_grid_no_zero_count_renders() -> None:
    """When a route has 0 providers, the tile's count is None and count_label is
    the empty string -- never "0 listed" (BUILD.md no-zero rule)."""

    class _ZeroQuery:
        def filter(self, *_a, **_kw):
            return self

        def scalar(self):
            return 0  # no providers on any route

    class _ZeroSession:
        def query(self, *_a, **_kw):
            return _ZeroQuery()

    cards = queries_c.services_grid(_ZeroSession())
    for card in cards:
        assert card["count"] is None
        assert card["count_label"] == ""
        assert "0 listed" not in card["count_label"]


def test_services_grid_swallows_db_exception() -> None:
    """A DB hiccup must not 500 /home. The function returns all 12
    tiles with no counts; the template still renders."""

    class _BrokenQuery:
        def filter(self, *_a, **_kw):
            raise RuntimeError("connection lost")

    class _BrokenSession:
        def query(self, *_a, **_kw):
            return _BrokenQuery()

    cards = queries_c.services_grid(_BrokenSession())
    assert len(cards) == 12
    for card in cards:
        assert card["count"] is None


# ---------------------------------------------------------------------------
# End-to-end render via TestClient
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_curated_caches() -> None:
    queries_c.reset_cache()
    yield
    queries_c.reset_cache()


def test_home_renders_sandstone_services_strip(seeded_nav_departments: dict) -> None:
    """The Sandstone home renders the 'Need something done?' service strip.

    A.3 nav rewire: the tiles are the service-side taxonomy departments, so
    every tile links a live ``/categories/{department}`` landing. The strip
    is honest-omission gated — it only renders when departments exist, hence
    the ``seeded_nav_departments`` fixture.
    """
    with TestClient(app) as client:
        resp = client.get("/home")
    assert resp.status_code == 200
    rendered = resp.text
    assert "/static/styles/desert.css" in rendered  # Desert Modern reskin
    assert "Need something done?" in rendered
    assert 'href="/categories/home-and-property-services"' in rendered
    assert "Professional" in rendered


def test_home_services_strip_has_no_zero_counts() -> None:
    """The service strip is a directory (no counts) -> never a '0 listed'."""
    with TestClient(app) as client:
        rendered = client.get("/home").text
    assert "0 listed" not in rendered
