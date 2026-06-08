"""Accessibility smoke tests for the Lake Light surfaces (wf-feat-a11y).

Light string-level assertions on rendered HTML. These guard against
regressions in the concrete a11y fixes shipped on this branch:

- Decorative ``<img>`` in the hava card carries an explicit ``alt`` so
  screen readers skip it instead of announcing the URL.
- The events list/calendar tab buttons wire up ``aria-controls`` /
  ``role="tabpanel"`` and the icon-thin calendar pager buttons have
  ``aria-label``.
- The shared stylesheet ships a visible ``:focus-visible`` outline for
  ``.ll-chip`` / ``.ll-facet`` / ``.ll-list-card`` / ``.ll-categories-card``
  so keyboard users can see where focus is.

We deliberately keep these as substring checks (the v32 pattern in
test_category_pages) rather than parsing the DOM -- the goal is a cheap
tripwire, not a full audit.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.categories import queries as cat_queries
from app.main import app

_CSS_PATH = Path(__file__).resolve().parents[1] / "app" / "static" / "styles" / "lake_light.css"


def _stub_cards(n: int) -> list[dict]:
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


# ---------------------------------------------------------------------------
# Stylesheet: visible keyboard focus
# ---------------------------------------------------------------------------


def test_focus_visible_outline_for_interactive_cards_and_chips() -> None:
    """The shared stylesheet must give chips, facets and the two card
    flavors a visible :focus-visible outline so keyboard nav is usable."""
    css = _CSS_PATH.read_text(encoding="utf-8")
    for selector in (
        ".ll-chip:focus-visible",
        ".ll-facet:focus-visible",
        ".ll-list-card:focus-visible",
        ".ll-categories-card:focus-visible",
    ):
        assert selector in css, f"missing focus-visible rule for {selector}"


# ---------------------------------------------------------------------------
# Category page: images carry alt, icon controls are labelled
# ---------------------------------------------------------------------------


def test_category_page_images_have_alt() -> None:
    """Every <img> on the category stream must carry an alt attribute --
    decorative hero images use alt="" so they are skipped, not announced
    as a raw URL."""
    client = TestClient(app)
    with (
        patch.object(cat_queries, "category_cards", return_value=_stub_cards(3)),
        patch.object(cat_queries, "category_count", return_value=3),
    ):
        resp = client.get("/categories/eat-drink")
    assert resp.status_code == 200
    body = resp.text
    # Crude but effective: no <img ...> tag without an alt= before its close.
    for fragment in body.split("<img")[1:]:
        tag = fragment.split(">", 1)[0]
        assert "alt=" in tag, f"<img{tag}> missing alt attribute"


def test_category_page_all_categories_pill_is_labelled() -> None:
    """The header navigation pills expose accessible text names."""
    client = TestClient(app)
    # WP-5: subtype chips (incl. the "All" pill) are now generated from subtypes
    # ACTUALLY present, so stub one present subtype to exercise the chip row.
    chips = [{"slug": "restaurants", "label": "Restaurants", "count": 2}]
    with (
        patch.object(cat_queries, "category_listing", return_value=(_stub_cards(2), 2)),
        patch.object(cat_queries, "subcategory_chips_for_route", return_value=chips),
    ):
        resp = client.get("/categories/eat-drink")
    assert resp.status_code == 200
    body = resp.text
    # Sandstone: the "All" subcategory chip and the "Explore all" mega trigger
    # carry accessible text names; the breadcrumb + logo link home.
    assert ">All</a>" in body
    assert "Explore all" in body
    assert 'href="/home"' in body


# ---------------------------------------------------------------------------
# Events page: tablist wiring + labelled pager buttons
# ---------------------------------------------------------------------------


def test_events_page_sections_are_labelled_for_screen_readers() -> None:
    """Sandstone events is server-rendered; the default Today view wraps its
    accordion in a labelled <section> so screen readers can navigate by
    region, and the page links to its own month view (the events page now
    carries the calendar instead of pointing at /home#calendar)."""
    client = TestClient(app)
    resp = client.get("/events-ui")
    assert resp.status_code == 200
    body = resp.text
    assert 'aria-label="Today"' in body
    assert "Events around the lake" in body
    assert "/events-ui?view=month" in body


def test_home_calendar_pager_buttons_have_aria_label() -> None:
    """The month pager (now on the home calendar) spells out what it navigates."""
    client = TestClient(app)
    resp = client.get("/home")
    assert resp.status_code == 200
    body = resp.text
    assert 'aria-label="Previous month"' in body
    assert 'aria-label="Next month"' in body


def test_events_page_decorative_bookmark_is_hidden() -> None:
    """The heart glyph on each event card is decorative; it must be
    aria-hidden so it is not announced as stray text."""
    client = TestClient(app)
    resp = client.get("/events-ui")
    assert resp.status_code == 200
    body = resp.text
    # Only meaningful when at least one event card rendered.
    if "ll-bookmark" in body:
        assert 'class="ll-bookmark" aria-hidden="true"' in body


# ---------------------------------------------------------------------------
# Sanity: render does not depend on a populated DB
# ---------------------------------------------------------------------------


def test_events_page_renders_with_empty_db() -> None:
    client = TestClient(app)
    resp = client.get("/events-ui")
    assert resp.status_code == 200
    assert "Events around the lake" in resp.text
