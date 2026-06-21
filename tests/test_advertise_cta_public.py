"""P0: the footer "Advertise" CTA must land on a PUBLIC page, not a login wall.

The most-linked advertise CTA (footer "Advertise", on every page) pointed at
``/portal/placements`` — a merchant dashboard that 303-redirects a logged-out
visitor to ``/login``. So a regular visitor clicking "Advertise" hit a login
wall. P0 repoints it to the public ``/sponsor`` advertiser landing (the page
``/advertise`` already canonicalizes to). These tests pin that the CTA is public
and that the old target really was gated (the reason we moved).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_footer_advertise_points_at_public_sponsor() -> None:
    for url in ("/home", "/home?theme=desert"):
        body = client.get(url).text
        assert 'href="/sponsor">Advertise' in body or 'href="/sponsor"' in body, url


def test_sponsor_landing_is_public_200() -> None:
    # No login wall: a logged-out visitor sees the advertiser landing directly.
    for url in ("/sponsor", "/sponsor?theme=lake"):
        r = client.get(url, follow_redirects=False)
        assert r.status_code == 200, (url, r.status_code)


def test_placements_dashboard_is_login_gated() -> None:
    # Documents WHY the CTA moved: the old target login-walls anonymous users.
    r = client.get("/portal/placements", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers.get("location", "")
