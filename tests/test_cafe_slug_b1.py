"""B1/B3 — café leaf slug rename + retired-flat-slug 301s.

The A.3 taxonomy seed shipped the ``Cafés & Coffee`` leaf as
``caf-s-and-coffee`` (slugifier dropped the ``é``). The data migration
renames the row to ``cafes-and-coffee``; the old URL must 301 permanently
(``LEAF_SLUG_ALIASES``), and the retired flat ``/categories/eat-drink``
keeps 301ing to the canonical department.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_old_cafe_leaf_slug_301s_to_canonical(client: TestClient) -> None:
    r = client.get(
        "/categories/eat-and-drink/caf-s-and-coffee", follow_redirects=False
    )
    assert r.status_code == 301
    assert r.headers["location"] == "/categories/eat-and-drink/cafes-and-coffee"


def test_old_cafe_leaf_slug_redirect_preserves_query(client: TestClient) -> None:
    r = client.get(
        "/categories/eat-and-drink/caf-s-and-coffee?open=1", follow_redirects=False
    )
    assert r.status_code == 301
    assert (
        r.headers["location"]
        == "/categories/eat-and-drink/cafes-and-coffee?open=1"
    )


def test_flat_eat_drink_route_301s_to_department(client: TestClient) -> None:
    # B3: the retired flat slug must never serve a 200 page again — it 301s
    # straight to the canonical taxonomy department.
    r = client.get("/categories/eat-drink", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/categories/eat-and-drink"
