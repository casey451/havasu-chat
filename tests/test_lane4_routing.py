"""Lane 4 routing: /ask -> /chat (1.2) and category slug aliases (1.5)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.categories.router import ROUTE_SLUG_ALIASES
from app.main import app


def test_ask_redirects_to_chat() -> None:
    # 1.2: /ask is a 302 (non-cached) redirect to the chat surface.
    client = TestClient(app)
    resp = client.get("/ask", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/chat"


def test_pets_and_vets_alias_redirects_to_pets() -> None:
    # 1.5: friendly slug -> the Pets department landing.
    client = TestClient(app)
    resp = client.get("/categories/pets-and-vets", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == "/categories/pets"
    assert ROUTE_SLUG_ALIASES["pets-and-vets"] == "/categories/pets"


def test_salons_and_spas_alias_redirects_to_beauty() -> None:
    # 1.5: "salons-and-spas" -> the beauty department (display label "Salons & Spas").
    client = TestClient(app)
    resp = client.get("/categories/salons-and-spas", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == "/categories/beauty-and-personal-care"
    assert ROUTE_SLUG_ALIASES["salons-and-spas"] == "/categories/beauty-and-personal-care"
