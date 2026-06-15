"""Business portal — landing + claim (Phase 2 §5b, no payments yet)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_portal_landing_renders() -> None:
    with TestClient(app) as client:
        r = client.get("/portal")
    assert r.status_code == 200
    # Desert Modern reskin: base tokens + the portal page stylesheet.
    assert "/static/styles/desert.css" in r.text
    assert "/static/styles/desert_portal.css" in r.text
    assert 'href="/portal/claim"' in r.text
    assert 'href="/portal/placements"' in r.text


def test_claim_entry_renders_no_dead_link() -> None:
    """The /portal/claim entry the landing links to must exist (not 404)."""
    with TestClient(app) as client:
        r = client.get("/portal/claim")
    assert r.status_code == 200
    assert "Claim your listing" in r.text
    assert "/contribute" in r.text  # add-a-business path


def test_no_payment_route_yet() -> None:
    """Stripe checkout is deferred — /portal/checkout must not exist yet."""
    with TestClient(app) as client:
        r = client.get("/portal/checkout", follow_redirects=False)
    assert r.status_code == 404
