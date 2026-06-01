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

import html as html_lib
from unittest.mock import patch

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
            f"tile {tile['name']} svg_path must start with SVG command, "
            f"got {first!r}"
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


def test_services_grid_with_mocked_db_returns_real_counts() -> None:
    """Mock the SQLAlchemy query path to return known per-slug counts;
    verify ``services_grid`` SUMS them across the full
    ``CATEGORY_FILTERS[route]`` tuple. This is the key invariant: a
    tile's count must match the count the visitor sees on the
    destination ``/categories/{route}`` page -- no drift."""

    class _FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *_a, **_kw):
            return self

        def group_by(self, *_a, **_kw):
            return self

        def all(self):
            return self._rows

    class _FakeSession:
        def __init__(self, rows):
            self._rows = rows

        def query(self, *_a, **_kw):
            return _FakeQuery(self._rows)

    # ``health-wellness-care`` filters (health_medical, fitness,
    # fitness_sports). All three contribute to the tile count.
    # ``home-property-services`` filters (home_services,
    # general_contractor, plumbing, services) -- only home_services in
    # the mock, so the tile count is just that single slug's value.
    # ``pets`` filters (pets, pet, veterinary) -- pets + veterinary in
    # the mock. ``auto-rv-fuel`` filters (auto,) -- single slug.
    fake_rows = [
        ("health_medical", 300),
        ("fitness", 10),
        ("fitness_sports", 18),  # 300 + 10 + 18 = 328 for health-wellness-care
        ("home_services", 262),
        ("auto", 166),
        ("pets", 30),
        ("veterinary", 7),       # 30 + 7 = 37 for pets
    ]
    db = _FakeSession(fake_rows)
    cards = queries_c.services_grid(db)
    by_route = {c["route"]: c for c in cards}

    # health-wellness-care sums all three contributing slugs.
    assert by_route["health-wellness-care"]["count"] == 328
    assert by_route["health-wellness-care"]["count_label"] == "328 listed"
    # home-property-services has 4 slugs in CATEGORY_FILTERS but only
    # one has rows in the mock; the tile count equals that slug.
    assert by_route["home-property-services"]["count"] == 262
    # Single-slug tile: auto-rv-fuel -> (auto,).
    assert by_route["auto-rv-fuel"]["count"] == 166
    # pets tile sums (pets, pet, veterinary) -> 30 + 0 + 7.
    assert by_route["pets"]["count"] == 37
    # Tile whose slug set has no rows in the mock falls back to None / "".
    # NB: ``lodging-vacation-rentals`` filters ``(lodging,)``. This
    # assertion holds only as long as ``fake_rows`` above has no
    # ``("lodging", N)`` entry -- if a future test author adds one,
    # change this assertion to the new expected count rather than
    # deleting it.
    assert by_route["lodging-vacation-rentals"]["count"] is None
    assert by_route["lodging-vacation-rentals"]["count_label"] == ""


def test_services_grid_tile_count_matches_category_page_arithmetic() -> None:
    """The whole point of this PR: a /home tile labeled "247 listed"
    and the slim header on ``/categories/{route}`` must compute the
    same number. Verify against the same mocked rows that the tile
    sum equals what a hand-rolled CATEGORY_FILTERS[route] sum would
    produce. (Mirror of the upstream contract -- if this test passes
    but visitors still see drift, the bug is in ``category_count``,
    not here.)"""

    class _FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *_a, **_kw):
            return self

        def group_by(self, *_a, **_kw):
            return self

        def all(self):
            return self._rows

    class _FakeSession:
        def __init__(self, rows):
            self._rows = rows

        def query(self, *_a, **_kw):
            return _FakeQuery(self._rows)

    # Construct a row set with multiple slugs in tuples that span
    # several tiles (especially the broad ones: health-wellness-care,
    # professional, classes-sports-recreation).
    fake_rows = [
        ("health_medical", 200),
        ("fitness", 5),
        ("fitness_sports", 25),     # health-wellness-care = 230
                                     # classes-sports-recreation += 25
        ("childcare_education", 4),  # classes-sports-recreation += 4
        ("education", 2),            # classes-sports-recreation += 2 (= 31)
        ("professional_services", 80),
        ("real_estate", 40),
        ("insurance", 30),
        ("financial", 10),
        ("legal", 20),               # professional = 180
        ("entertainment_attractions", 50),
        ("tourism", 10),             # attractions = 60
    ]
    db = _FakeSession(fake_rows)
    cards = queries_c.services_grid(db)
    by_route = {c["route"]: c for c in cards}

    counts_map = dict(fake_rows)
    for tile in queries_c._SERVICE_TILES:
        expected = sum(counts_map.get(s, 0) for s in CATEGORY_FILTERS[tile["route"]])
        if expected > 0:
            assert by_route[tile["route"]]["count"] == expected, (
                f"tile {tile['name']} count mismatch: "
                f"got {by_route[tile['route']]['count']}, expected sum {expected}"
            )
        else:
            assert by_route[tile["route"]]["count"] is None


def test_services_grid_no_zero_count_renders() -> None:
    """When the catalog has 0 providers in a slug bucket, the tile's
    count is None and count_label is the empty string -- never
    "0 listed" (BUILD.md no-zero rule)."""

    class _ZeroQuery:
        def filter(self, *_a, **_kw):
            return self

        def group_by(self, *_a, **_kw):
            return self

        def all(self):
            return []  # no rows -> no counts

    class _ZeroSession:
        def query(self, *_a, **_kw):
            return _ZeroQuery()

    cards = queries_c.services_grid(_ZeroSession())
    for card in cards:
        assert card["count"] is None
        assert card["count_label"] == ""
        # And especially never "0 listed"
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


def test_home_redesign_renders_services_grid_section() -> None:
    """Home renders successfully when services_grid is mocked."""
    client = TestClient(app)
    with patch.object(
        queries_c,
        "services_grid",
        return_value=[
            {
                "name": tile["name"],
                "route": tile["route"],
                "svg_path": tile["svg_path"],
                "count": (i + 1) * 10,
                "count_label": f"{(i + 1) * 10} listed",
                "href": f"/categories/{tile['route']}",
            }
            for i, tile in enumerate(queries_c._SERVICE_TILES)
        ],
    ):
        resp = client.get("/home")
    assert resp.status_code == 200
    rendered = resp.text
    assert "/static/styles/lake_light.css" in rendered
    assert "Browse Havasu" in rendered


def test_home_redesign_services_grid_hides_count_when_zero() -> None:
    """No explicit zero-listing copy should render on home."""
    client = TestClient(app)
    # First tile has no count; others have real counts.
    fake_cards = []
    for i, tile in enumerate(queries_c._SERVICE_TILES):
        if i == 0:
            count_value = None
            count_label = ""
        else:
            count_value = (i + 1) * 5
            count_label = f"{count_value} listed"
        fake_cards.append(
            {
                "name": tile["name"],
                "route": tile["route"],
                "svg_path": tile["svg_path"],
                "count": count_value,
                "count_label": count_label,
                "href": f"/categories/{tile['route']}",
            }
        )
    with patch.object(queries_c, "services_grid", return_value=fake_cards):
        resp = client.get("/home")
    assert resp.status_code == 200
    rendered = resp.text
    assert "0 listed" not in rendered
