"""UX-1: homepage one-line trust strip (site-wide footer row).

The original above-the-fold quick-intent chips + hero/intents/explore fold-order
were part of the desert/sandstone home and were removed in the Lake home
redesign; only the still-true trust-strip behavior remains under test here."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_home_has_trust_strip_linked() -> None:
    # §2.3: the trust line was relocated from the hero to a site-wide footer row,
    # so the phrases + their substantiating links still appear in the page body.
    r = client.get("/home")
    body = r.text
    assert "Real public reviews" in body
    assert "Sponsored clearly labeled" in body
    assert "Built in Lake Havasu" in body
    assert 'href="/about"' in body
    # "Sponsored clearly labeled" → the public /sponsor advertiser page (was the
    # auth-gated /portal/placements, which login-walled the most-linked CTA).
    assert 'href="/sponsor"' in body
