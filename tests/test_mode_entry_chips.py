"""Mode-page discovery — homepage entry chips for /lake and /night.

The /lake (Lake Life) and /night (after-dark) mode landings were live but only
reachable via the in-page mode switcher — no homepage/nav entry point (only
/family had one, via the "Kid-friendly" chip). These add the missing entry
points, and the chips must point at pages that actually exist (the row's
no-confabulation rule).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_home_has_lake_and_night_intent_chips() -> None:
    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    body = r.text
    assert 'href="/lake"' in body, "missing /lake entry chip on home"
    assert 'href="/night"' in body, "missing /night entry chip on home"


def test_mode_landing_routes_exist() -> None:
    """Every entry chip must resolve — the chips point at real surfaces only."""
    with TestClient(app) as client:
        for path in ("/lake", "/night", "/family"):
            r = client.get(path)
            assert r.status_code == 200, f"{path} should render (chip target must exist)"
