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


# The home /lake + /night entry chips were part of the desert/sandstone home
# above-the-fold chip row, removed in the Lake home redesign. Only the
# route-existence contract (every chip target must resolve) remains under test.
def test_mode_landing_routes_exist() -> None:
    """Every entry chip must resolve. WS10 rebuilt /lake as a content hub (it had
    briefly 301'd to the Lake Life category under C11); /lake, /night and /family
    all render their hub now."""
    with TestClient(app) as client:
        for path in ("/lake", "/night", "/family"):
            r = client.get(path, follow_redirects=False)
            assert r.status_code == 200, f"{path} should render (chip target must exist)"
