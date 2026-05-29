"""Q2 -- ``GET /categories`` index page (v48, 2026-05-29).

Coverage:

1. Data-shape invariants on ``_build_index_payload`` --
   - row count equals ``len(CATEGORY_FILTERS)`` (15, not 16; the audit
     handoff mis-counted, ``test_category_pages.test_category_filters_has_expected_route_count``
     pins this to 15).
   - every row carries slug, label, blurb, count, peek_images,
     empty_blurb in the documented shapes.
   - slug set matches ``CATEGORY_FILTERS`` keys exactly (no drift, no
     extra entries).
   - counts are non-negative ints.

2. Defensive DB error handling --
   - ``_category_count`` swallows a DB exception to 0.
   - ``_peek_provider`` swallows a DB exception to None.

3. Cache behavior --
   - Calling ``_get_index_payload`` twice in the TTL window returns
     the *same object* (identity) -- proves the cache is hit, not
     just structurally identical.
   - ``reset_index_cache()`` actually clears the cache, so the next
     call rebuilds.

4. End-to-end --
   - GET /categories returns 200.
   - Every category label appears in the rendered body.
   - The "All categories" topbar link is present and active.

Autouse cache-reset fixture mirrors
``tests/test_robots_and_sitemap.py::_clear_sitemap_cache`` so module
state never leaks across cases.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.categories import router as cat_router
from app.categories.queries import CATEGORY_DISPLAY, CATEGORY_FILTERS
from app.db.database import SessionLocal
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_index_cache() -> None:
    """Reset the module-level /categories cache between tests."""
    cat_router.reset_index_cache()
    yield
    cat_router.reset_index_cache()


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _BoomDB:
    """Minimal DB stub whose ``query()`` always raises.

    Used to exercise the try/except in ``_category_count`` and
    ``_peek_provider`` without spinning up a session.
    """

    def query(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("simulated DB outage")


# ---------------------------------------------------------------------------
# Data-shape invariants
# ---------------------------------------------------------------------------


def test_build_index_payload_row_count_matches_filters() -> None:
    """One row per CATEGORY_FILTERS key. The audit handoff mis-counted
    these as 16; the existing invariant test pins it to 15."""
    with SessionLocal() as db:
        payload = cat_router._build_index_payload(db)
    assert len(payload) == len(CATEGORY_FILTERS)
    assert len(payload) == 15


def test_build_index_payload_row_shape() -> None:
    """Every row carries the documented keys with the documented types."""
    with SessionLocal() as db:
        payload = cat_router._build_index_payload(db)
    for row in payload:
        assert isinstance(row, dict)
        assert isinstance(row["slug"], str) and row["slug"]
        assert isinstance(row["label"], str) and row["label"]
        assert isinstance(row["blurb"], str) and row["blurb"]
        assert isinstance(row["count"], int)
        assert row["count"] >= 0
        assert isinstance(row["peek_images"], list)
        for peek in row["peek_images"]:
            assert isinstance(peek, dict)
            assert "url" in peek and "name" in peek
        assert isinstance(row["empty_blurb"], str) and row["empty_blurb"]


def test_build_index_payload_slugs_match_filters_exactly() -> None:
    """No drift, no extra entries -- slug set is exactly CATEGORY_FILTERS."""
    with SessionLocal() as db:
        payload = cat_router._build_index_payload(db)
    assert {row["slug"] for row in payload} == set(CATEGORY_FILTERS.keys())


def test_build_index_payload_labels_match_display_copy() -> None:
    """Labels come from CATEGORY_DISPLAY -- no silent rewording."""
    with SessionLocal() as db:
        payload = cat_router._build_index_payload(db)
    for row in payload:
        if row["slug"] in CATEGORY_DISPLAY:
            expected_label, _ = CATEGORY_DISPLAY[row["slug"]]
            assert row["label"] == expected_label


# ---------------------------------------------------------------------------
# Defensive DB error handling
# ---------------------------------------------------------------------------


def test_category_count_swallows_db_exception_to_zero() -> None:
    """A DB outage during the COUNT must degrade to 0, not 500."""
    result = cat_router._category_count(_BoomDB(), ("food",))
    assert result == 0


def test_category_count_empty_slug_tuple_returns_zero() -> None:
    """Defensive: an empty slug tuple short-circuits to 0 (no query)."""
    # _BoomDB would raise if .query were ever called -- this proves
    # the empty-tuple branch never reaches the DB.
    result = cat_router._category_count(_BoomDB(), ())
    assert result == 0


def test_peek_provider_swallows_db_exception_to_none() -> None:
    """A DB outage during the peek query must return None, not 500."""
    result = cat_router._peek_provider(_BoomDB(), ("food",))
    assert result is None


def test_peek_provider_empty_slug_tuple_returns_none() -> None:
    """Empty slug tuple short-circuits to None without touching the DB."""
    result = cat_router._peek_provider(_BoomDB(), ())
    assert result is None


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------


def test_get_index_payload_caches_within_ttl_window() -> None:
    """Two calls in the TTL window must return the same object.

    Identity check (``is``) -- a fresh list with identical contents
    would still pass an equality check but would prove the cache was
    bypassed, so we want the stronger guarantee.
    """
    with SessionLocal() as db:
        first = cat_router._get_index_payload(db)
        second = cat_router._get_index_payload(db)
    assert first is second


def test_get_index_payload_rebuilds_after_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reset_index_cache() forces the next call to rebuild.

    We count invocations of _build_index_payload to prove the cache
    actually clears -- a no-op reset would let the second call hit
    the cached payload and the counter would stay at 1.
    """
    calls = {"n": 0}
    real_build = cat_router._build_index_payload

    def _counting_build(db):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return real_build(db)

    monkeypatch.setattr(cat_router, "_build_index_payload", _counting_build)

    with SessionLocal() as db:
        cat_router._get_index_payload(db)
        assert calls["n"] == 1
        # Second call inside the window: cached -> still 1.
        cat_router._get_index_payload(db)
        assert calls["n"] == 1
        # After reset, next call rebuilds.
        cat_router.reset_index_cache()
        cat_router._get_index_payload(db)
        assert calls["n"] == 2


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------


def test_get_categories_index_returns_200(client: TestClient) -> None:
    r = client.get("/categories")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_get_categories_index_renders_every_label(client: TestClient) -> None:
    """Every CATEGORY_DISPLAY label must appear in the rendered body --
    the index would be a lie if any route silently dropped.

    Labels with ampersands are HTML-escaped at render time
    (``Eat & drink`` -> ``Eat &amp; drink``), so the assertion checks
    the escaped form to match what Jinja autoescape emits.
    """
    import html as _html

    r = client.get("/categories")
    assert r.status_code == 200
    body = r.text
    for slug, (label, _) in CATEGORY_DISPLAY.items():
        escaped = _html.escape(label)
        assert escaped in body, f"missing label {label!r} for slug {slug!r}"


def test_get_categories_index_has_all_categories_topbar_link(
    client: TestClient,
) -> None:
    """The new fifth topbar link is present AND marked active."""
    r = client.get("/categories")
    assert r.status_code == 200
    body = r.text
    # Link is present.
    assert "All categories" in body
    # And it carries is-active + aria-current on this page.
    assert "c-tab-all" in body
    assert "is-active" in body
    assert 'aria-current="page"' in body


def test_get_categories_index_links_to_each_category_page(
    client: TestClient,
) -> None:
    """Every card must link to /categories/<slug>."""
    r = client.get("/categories")
    body = r.text
    for slug in CATEGORY_FILTERS:
        assert f'href="/categories/{slug}"' in body, (
            f"missing /categories/{slug} card link in index"
        )
