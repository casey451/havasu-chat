"""WS10 — /lake is a real hub again (was the C11 redirect to the category).

C11 had ``/lake`` 301 to ``/categories/on-the-water`` (the two were duplicate
surfaces). WS10 (§10) rebuilds ``/lake`` as a content hub — live conditions +
launch ramps + the on-the-water subcategory lists — while the full directory
stays at that category URL and is linked from the hub, so the two are now
complementary rather than duplicates.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.home.router import LAKE_LIFE_CATEGORY_URL
from app.main import app


def test_lake_renders_hub_not_redirect() -> None:
    client = TestClient(app)
    resp = client.get("/lake", follow_redirects=False)
    assert resp.status_code == 200
    # The hub LINKS to the full directory (the old redirect target) instead of
    # 301-ing to it.
    assert LAKE_LIFE_CATEGORY_URL in resp.text


def test_night_and_family_still_render() -> None:
    client = TestClient(app)
    for mode in ("/night", "/family"):
        assert client.get(mode).status_code == 200
