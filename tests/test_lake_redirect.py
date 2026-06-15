"""C11 — /lake merged into the Lake Life directory category.

The curated ``/lake`` mode landing and the ``on-the-water`` ("Lake Life")
category were duplicate surfaces; ``/lake`` now 301-redirects to the canonical
category so the inbound URL keeps working with a single page behind it.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.home.router import LAKE_LIFE_CATEGORY_URL
from app.main import app


def test_lake_permanently_redirects_to_category() -> None:
    client = TestClient(app)
    resp = client.get("/lake", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == LAKE_LIFE_CATEGORY_URL == "/categories/on-the-water"


def test_night_and_family_still_render() -> None:
    # The merge only touches /lake; the other mode landings keep serving 200.
    client = TestClient(app)
    for mode in ("/night", "/family"):
        assert client.get(mode).status_code == 200
