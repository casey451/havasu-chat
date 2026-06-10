"""Sandstone /home redesign tests (replaces the Lake Light home).

The home page is now the Sandstone editorial home (``home_sandstone.html``).
These assert the locked design markers + the anti-confabulation contract: no
mock counts, every section wired to live data or omitted.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_home_serves_desert_by_default() -> None:
    # Desert Modern reskin: the home wears the desert base (desert.css + the
    # sun-over-ridge logotype) — same data-mode + ask-form contracts as before.
    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    assert "/static/styles/desert.css" in r.text
    assert 'data-mode="ask"' in r.text
    assert "Ask&nbsp;Hava" in r.text
    assert 'id="home-ask-form"' in r.text


def test_home_calendar_param_still_serves_desert() -> None:
    with TestClient(app) as client:
        for path in ("/home?cal=2026-07", "/home?cal=2026-01"):
            r = client.get(path)
            assert r.status_code == 200
            assert "/static/styles/desert.css" in r.text


def test_sandstone_no_mock_content() -> None:
    """The prototype's hardcoded numbers must never reach production."""
    with TestClient(app) as client:
        r = client.get("/home")
    for leaked in ("12 happy hours", "280 places", "448.7", "6 kid events"):
        assert leaked not in r.text, f"home leaked mock content: {leaked}"
    for leaked in ("Channel Brewing Co.", "Havasu Outdoor Co."):
        assert leaked not in r.text


def test_sandstone_has_explore_and_nav(seeded_nav_departments: dict) -> None:
    with TestClient(app) as client:
        r = client.get("/home")
    assert 'href="/categories"' in r.text
    assert "Explore all" in r.text
    assert "Explore Havasu" in r.text
