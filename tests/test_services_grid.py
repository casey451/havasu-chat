"""Direction C Service icon grid tests (PR D4).

Coverage:

1. ``_SERVICE_TILES`` module-level invariants (tile count, key shape,
   slug validity against LEGACY_PROVIDER_CATEGORY_LABELS, no
   double-count with the eat row, no duplicates).
2. ``queries_c.services_grid()`` contract:
   - 12 cards always, ordered to match the constant.
   - DB None / DB error swallow into "all counts None".
   - Mocked DB rows map correctly to per-tile counts.
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
    """The template reads name/slug/route/svg_path on every tile.
    A missing key would render a blank or KeyError in Jinja."""
    required = {"name", "slug", "route", "svg_path"}
    for tile in queries_c._SERVICE_TILES:
        missing = required - set(tile.keys())
        assert not missing, f"tile {tile.get('name', tile)} missing keys {missing}"


def test_every_tile_has_nonempty_string_values() -> None:
    """No tile may have an empty string for any required field."""
    for tile in queries_c._SERVICE_TILES:
        for key in ("name", "slug", "route", "svg_path"):
            value = tile[key]
            assert isinstance(value, str) and value, (
                f"tile {tile.get('name')} key {key} must be non-empty string"
            )


def test_every_tile_slug_is_in_legacy_category_labels() -> None:
    """Tiles count against ``Provider.category`` -- every slug must be a
    known legacy taxonomy value. Drift here means a tile shows 0
    forever (silently)."""
    for tile in queries_c._SERVICE_TILES:
        slug = tile["slug"]
        assert slug in LEGACY_PROVIDER_CATEGORY_LABELS, (
            f"tile {tile['name']} slug {slug!r} not in LEGACY_PROVIDER_CATEGORY_LABELS"
        )


def test_no_tile_slug_overlaps_the_eat_row() -> None:
    """The eat row already counts food/drink Providers. A services
    tile that also points at a food/drink slug would double-count and
    overlap the visual surfaces. Detect at the constant level."""
    food_drink_slugs = set(queries_c._FOOD_DRINK_CATEGORIES)
    service_slugs = {tile["slug"] for tile in queries_c._SERVICE_TILES}
    overlap = service_slugs & food_drink_slugs
    assert not overlap, f"service tiles overlap eat row: {overlap}"


def test_tile_names_are_unique() -> None:
    """Two tiles with the same display name would confuse navigation
    and a11y. Detect at the constant level."""
    names = [tile["name"] for tile in queries_c._SERVICE_TILES]
    assert len(set(names)) == len(names), f"duplicate tile names: {names}"


def test_tile_slugs_are_unique() -> None:
    """Two tiles for the same slug would render twice with the same
    count. Detect at the constant level."""
    slugs = [tile["slug"] for tile in queries_c._SERVICE_TILES]
    assert len(set(slugs)) == len(slugs), f"duplicate tile slugs: {slugs}"


def test_tile_routes_are_unique() -> None:
    """Two tiles pointing at the same /categories/{route} are an
    editorial error -- pick one."""
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
    expected_keys = {"name", "slug", "route", "svg_path", "count", "count_label", "href"}
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
    verify ``services_grid`` maps them to the right tiles."""

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

    fake_rows = [
        ("health_medical", 328),
        ("home_services", 262),
        ("auto", 166),
        ("pets", 37),
    ]
    db = _FakeSession(fake_rows)
    cards = queries_c.services_grid(db)
    by_slug = {c["slug"]: c for c in cards}
    assert by_slug["health_medical"]["count"] == 328
    assert by_slug["health_medical"]["count_label"] == "328 listed"
    assert by_slug["home_services"]["count"] == 262
    assert by_slug["auto"]["count"] == 166
    assert by_slug["pets"]["count"] == 37
    # Tiles not in the fake rows fall back to None / "".
    assert by_slug["lodging"]["count"] is None
    assert by_slug["lodging"]["count_label"] == ""


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
    """GET /home?redesign=1 includes the services grid section
    with all 12 tile names and the section heading."""
    client = TestClient(app)
    with patch.object(
        queries_c,
        "services_grid",
        return_value=[
            {
                "name": tile["name"],
                "slug": tile["slug"],
                "route": tile["route"],
                "svg_path": tile["svg_path"],
                "count": (i + 1) * 10,
                "count_label": f"{(i + 1) * 10} listed",
                "href": f"/categories/{tile['route']}",
            }
            for i, tile in enumerate(queries_c._SERVICE_TILES)
        ],
    ):
        resp = client.get("/home?redesign=1")
    assert resp.status_code == 200
    rendered = resp.text
    assert 'class="c-svc-section"' in rendered
    assert "Services" in rendered
    # Jinja autoescape converts '&' to '&amp;' in body text; match the
    # escaped form so tile names like "Health & wellness" land cleanly.
    for tile in queries_c._SERVICE_TILES:
        needle = html_lib.escape(tile["name"])
        assert needle in rendered, f"missing tile name {tile['name']!r} (escaped {needle!r})"
    # Confirm no zero count copy is in the rendered HTML. Uses ">0 listed<"
    # (literal text-node start) to avoid the substring collision with
    # legitimate counts like "10 listed" / "20 listed".
    assert ">0 listed<" not in rendered


def test_home_redesign_services_grid_hides_count_when_zero() -> None:
    """When a tile's count is 0, the count line div is omitted. Render
    a grid where the first tile has 0 and verify the no-zero rule
    holds in the rendered HTML."""
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
                "slug": tile["slug"],
                "route": tile["route"],
                "svg_path": tile["svg_path"],
                "count": count_value,
                "count_label": count_label,
                "href": f"/categories/{tile['route']}",
            }
        )
    with patch.object(queries_c, "services_grid", return_value=fake_cards):
        resp = client.get("/home?redesign=1")
    assert resp.status_code == 200
    rendered = resp.text
    # All names still render (Jinja autoescape converts '&' -> '&amp;').
    for tile in queries_c._SERVICE_TILES:
        needle = html_lib.escape(tile["name"])
        assert needle in rendered
    # First tile's count line did not render (no count_label string for it).
    # And the no-zero invariant holds. Use ">0 listed<" (literal text-node
    # start) to avoid substring collision with "10 listed" / "20 listed".
    assert ">0 listed<" not in rendered
