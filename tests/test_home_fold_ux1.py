"""UX-1: homepage above-the-fold — quick-intent chips + one-line trust strip
inserted between the hero and the existing modules. Chips must point only at
real, existing surfaces (anti-confabulation)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_home_has_quick_intent_chips() -> None:
    r = client.get("/home")
    assert r.status_code == 200
    body = r.text
    for href in (
        "/chat?q=find+a+service",
        '"/events-ui"',
        "/events-ui?view=week",
        "/categories/on-the-water",
        '"/family"',
    ):
        assert href in body, href
    for label in ("Need a service", "Tonight", "This weekend", "On the water", "Kid-friendly"):
        assert label in body, label


def test_home_has_trust_strip_linked() -> None:
    r = client.get("/home")
    body = r.text
    assert "Real public reviews" in body
    assert "Sponsored clearly labeled" in body
    assert "Built in Lake Havasu" in body
    assert 'href="/about"' in body
    assert 'href="/portal/advertise"' in body


def test_fold_order_hero_then_intents_then_modules() -> None:
    """Chips + trust sit AFTER the hero and BEFORE the existing modules
    (the marquee section always renders, so it's a stable anchor)."""
    body = client.get("/home").text
    hero = body.index("home-hero")
    intents = body.index("home-intents")
    trust = body.index("home-trust")
    marquee = body.index("home-marquee")
    assert hero < intents < trust < marquee
