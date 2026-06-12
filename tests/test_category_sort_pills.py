"""2.9 cheap-v1 — Top-rated filter pill on the Sandstone category bar.

The eat-&-drink-style pages already parsed the ``rating`` facet
(``_facets_from_query`` → ``CategoryFacets.top_rated`` → applied in
``category_listing``) but never surfaced a control for it, while the trade bar
shows a "Top rated" pill. This adds the missing pill (parity), as a *filter*
(it narrows; it isn't a sort), wired to the existing ``rating`` param.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.main import app


def test_top_rated_filter_pill_present_and_toggles_rating_param() -> None:
    with TestClient(app) as client:
        r = client.get("/lake-havasu/restaurants")
    assert r.status_code == 200
    body = r.text
    assert ">Top rated</a>" in body, "Top rated filter pill missing from sandstone bar"
    # The pill toggles the rating facet on.
    assert "rating=1" in body


def test_rating_param_marks_top_rated_pill_active() -> None:
    """``?rating=1`` round-trips: the backend accepts it and the pill shows active."""
    with TestClient(app) as client:
        r = client.get("/lake-havasu/restaurants?rating=1")
    assert r.status_code == 200
    body = r.text
    # The Top-rated pill carries the active ``on`` class when the facet is set.
    # The anchor also carries an ``href`` (the toggle-off link), so match across it.
    assert re.search(r'class="filterpill on"[^>]*>Top rated</a>', body), body
