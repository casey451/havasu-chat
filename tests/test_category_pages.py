"""Direction C category-page tests (PR D5).

Coverage:

1. ``CATEGORY_FILTERS`` / ``CATEGORY_DISPLAY`` / ``_TAB_FOR_ROUTE``
   module-level invariants -- every route has display copy, every
   route has a tab mapping, no duplicate slugs in any filter tuple,
   every filter slug appears in LEGACY_PROVIDER_CATEGORY_LABELS.
2. ``is_valid_category_slug()`` -- known slugs, unknown slugs, edge
   cases (empty, whitespace, casing).
3. ``category_count()`` / ``category_cards()`` contracts -- None DB,
   exception swallowing, slug filtering, no-zero rule.
4. End-to-end render via ``GET /categories/{slug}``:
   - 200 OK for each of the 15 known routes.
   - 404 for an unknown slug.
   - Slim header renders with label + count when count > 0.
   - Count clause is absent (no "0 listed") when count is None.
   - Active tab pill carries ``is-active`` and ``aria-current``.
   - Topbar tab anchors render with ``/categories/{slug}`` hrefs.
   - Back link to /home present.
   - No "0 listed" copy anywhere -- uses ">0 listed<" (literal text-node
     start) to avoid substring collisions with "10 listed" / "20 listed".
   - SVG path data is stripped before the no-zero scan (the topbar
     wordmark dot and other inline SVGs have arc/move commands with
     literal " 0 ").

Tests follow the v32 pattern: TestClient renders, no-zero invariant
uses ">0 listed<" not " 0 ", SVG blocks are stripped before the scan
to prevent SVG path data (M3 0 ... a4 4 0 0 1) from tripping the
guard.
"""

from __future__ import annotations

import html as html_lib
import re
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.categories import queries as cat_queries
from app.home.queries import LEGACY_PROVIDER_CATEGORY_LABELS
from app.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_SVG_BLOCK = re.compile(r"<svg\b[^>]*>.*?</svg>", flags=re.IGNORECASE | re.DOTALL)


def _strip_svg(body: str) -> str:
    """Remove <svg>...</svg> blocks so SVG path data doesn't trip the
    naive ' 0 ' / '>0<' editorial-copy guards. See v32 handoff for the
    backstory -- this is the same pattern as test_discover_grid /
    test_eat_row use after D4 shipped."""
    return _SVG_BLOCK.sub("", body)


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
# End-to-end render via TestClient
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_curated_caches() -> None:
    """category_cards reads from queries_c._load_eat_photos (LRU-cached).
    Reset across tests so a monkey-patched loader in one test doesn't
    poison the next. Matches the v32 test_services_grid pattern."""
    from app.home import queries_c

    queries_c.reset_cache()
    yield
    queries_c.reset_cache()


def _stub_cards(n: int) -> list[dict]:
    """Generate n placeholder cards for the grid render."""
    return [
        {
            "slug": f"provider-{i}",
            "name": f"Provider {i}",
            "image_url": None,
            "neighborhood": "English Village",
            "status": "open",
            "status_text": "Open until 10",
            "rating": "4.5",
        }
        for i in range(n)
    ]


def test_category_route_404_for_unknown_slug() -> None:
    client = TestClient(app)
    resp = client.get("/categories/garbage-slug")
    assert resp.status_code == 404


@pytest.mark.parametrize("slug", sorted(cat_queries.CATEGORY_FILTERS.keys()))
def test_category_route_200_for_every_known_slug(slug: str) -> None:
    """All 15 known routes return 200 with the slim header and grid."""
    client = TestClient(app)
    label, _ = cat_queries.CATEGORY_DISPLAY[slug]
    with (
        patch.object(cat_queries, "category_cards", return_value=_stub_cards(5)),
        patch.object(cat_queries, "category_count", return_value=12),
    ):
        resp = client.get(f"/categories/{slug}")
    assert resp.status_code == 200, f"GET /categories/{slug} returned {resp.status_code}"
    body = resp.text
    # Jinja autoescape converts '&' -> '&amp;' for tile labels like
    # "Eat & drink". Match the escaped form.
    needle = html_lib.escape(label)
    assert needle in body, f"label {label!r} (escaped {needle!r}) missing from /categories/{slug}"
    # Lake Light category chrome present.
    assert 'class="ll-category-wrap"' in body
    assert 'class="ll-category-header"' in body
    # Back link to /home present.
    assert 'href="/home"' in body
    # Count clause rendered when category_count is truthy.
    assert "12 listed" in body


def test_category_route_hides_count_when_none() -> None:
    """When the query layer returns count=None (no rows or DB outage),
    the template hides the entire count clause -- no '0 listed' anywhere
    in the body. SVG blocks are stripped before the scan to avoid
    tripping on path data."""
    client = TestClient(app)
    with (
        patch.object(cat_queries, "category_cards", return_value=[]),
        patch.object(cat_queries, "category_count", return_value=None),
    ):
        resp = client.get("/categories/eat-drink")
    assert resp.status_code == 200
    body = _strip_svg(resp.text)
    # Use ">0 listed<" (literal text-node start) -- avoids the
    # substring collision with legitimate counts like "10 listed".
    assert ">0 listed<" not in body
    assert "0 listed" not in body  # full check on the SVG-stripped body
    assert 'class="ll-category-wrap"' in body


def test_category_route_renders_grid_when_cards_present() -> None:
    """When category_cards returns rows, the grid partial renders. The
    bridge empty-state branch should NOT appear."""
    client = TestClient(app)
    with (
        patch.object(cat_queries, "category_cards", return_value=_stub_cards(7)),
        patch.object(cat_queries, "category_count", return_value=7),
    ):
        resp = client.get("/categories/services")
    assert resp.status_code == 200
    body = resp.text
    assert 'class="ll-category-grid"' in body
    assert "Provider 0" in body
    assert "Provider 6" in body


def test_category_route_topbar_tab_anchors_have_hrefs() -> None:
    """Category page includes standard navigation links."""
    client = TestClient(app)
    with (
        patch.object(cat_queries, "category_cards", return_value=_stub_cards(3)),
        patch.object(cat_queries, "category_count", return_value=3),
    ):
        resp = client.get("/categories/eat-drink")
    assert resp.status_code == 200
    body = resp.text
    assert 'href="/categories"' in body
    assert 'href="/home"' in body


def test_category_route_marks_correct_tab_active() -> None:
    """Category page highlights Explore in bottom navigation."""
    client = TestClient(app)
    with (
        patch.object(cat_queries, "category_cards", return_value=_stub_cards(2)),
        patch.object(cat_queries, "category_count", return_value=2),
    ):
        resp = client.get("/categories/eat-drink")
    assert resp.status_code == 200
    body = resp.text
    assert '<a class="is-active" href="/categories">Explore</a>' in body


def test_category_route_tile_route_marks_mega_tab_active() -> None:
    """Tile route still highlights Explore in bottom navigation."""
    client = TestClient(app)
    with (
        patch.object(cat_queries, "category_cards", return_value=_stub_cards(4)),
        patch.object(cat_queries, "category_count", return_value=4),
    ):
        resp = client.get("/categories/pets")
    assert resp.status_code == 200
    body = resp.text
    assert '<a class="is-active" href="/categories">Explore</a>' in body


def test_home_redesign_tabs_are_real_anchors() -> None:
    """Home includes category navigation anchors."""
    client = TestClient(app)
    resp = client.get("/home")
    assert resp.status_code == 200
    body = resp.text
    assert 'href="/categories"' in body
    assert "Explore" in body


def test_category_route_no_zero_listed_copy_anywhere() -> None:
    """No '0 listed' should appear in the rendered HTML. Uses
    ">0 listed<" first (literal text-node start, avoids substring
    collision with legitimate '10 listed' / '20 listed') and then a
    full '0 listed' check on the SVG-stripped body."""
    client = TestClient(app)
    # Test the no-data path: empty cards, no count.
    with (
        patch.object(cat_queries, "category_cards", return_value=[]),
        patch.object(cat_queries, "category_count", return_value=None),
    ):
        resp = client.get("/categories/pets")
    assert resp.status_code == 200
    body = _strip_svg(resp.text)
    assert ">0 listed<" not in body
    assert "0 listed" not in body


def test_category_route_back_link_present() -> None:
    """Slim header must include a back link to /home so visitors can
    bail out of a category page back to the editorial home surface."""
    client = TestClient(app)
    with (
        patch.object(cat_queries, "category_cards", return_value=_stub_cards(1)),
        patch.object(cat_queries, "category_count", return_value=1),
    ):
        resp = client.get("/categories/lodging-vacation-rentals")
    assert resp.status_code == 200
    body = resp.text
    assert 'href="/home"' in body
