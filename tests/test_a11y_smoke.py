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
    with (
        patch.object(cat_queries, "category_cards", return_value=_stub_cards(2)),
        patch.object(cat_queries, "category_count", return_value=2),
    ):
        resp = client.get("/categories/eat-drink")
    assert resp.status_code == 200
    body = resp.text
    assert "All categories" in body
    # Back-to-home pill keeps an explicit aria-label.
    assert 'aria-label="Back to Hava home"' in body


# ---------------------------------------------------------------------------
# Events page: tablist wiring + labelled pager buttons
# ---------------------------------------------------------------------------


def test_events_page_tabs_are_wired_for_screen_readers() -> None:
    """The List/Calendar toggle is a real tablist: each tab points at its
    panel via aria-controls and each panel is a labelled tabpanel."""
    client = TestClient(app)
    resp = client.get("/events-ui")
    assert resp.status_code == 200
    body = resp.text
    assert 'aria-controls="events-list-panel"' in body
    assert 'aria-controls="events-calendar-panel"' in body
    assert 'role="tabpanel"' in body


def test_events_page_calendar_pager_buttons_have_aria_label() -> None:
    """'Prev'/'Next' lack context on their own -- the month pager buttons
    must spell out what they navigate."""
    client = TestClient(app)
    resp = client.get("/events-ui")
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
    assert 'role="tablist"' in resp.text
