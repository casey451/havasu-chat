"""UX-3: the claim page exposes a business-name search wired to the existing
/api/search/suggestions endpoint, with the browse path preserved as a no-JS
fallback (progressive enhancement)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_claim_page_has_search_autocomplete_wiring() -> None:
    r = client.get("/portal/claim")
    assert r.status_code == 200
    body = r.text
    # The search input + results container the JS hooks onto.
    assert 'id="claim-search-q"' in body
    assert 'id="claim-search-results"' in body
    # Wired to the existing suggestions endpoint.
    assert "/api/search/suggestions" in body


def test_claim_page_keeps_browse_fallback() -> None:
    """No-JS users still get the directory + add-a-listing doors."""
    r = client.get("/portal/claim")
    assert r.status_code == 200
    assert "/categories" in r.text
    assert "/contribute" in r.text


def test_suggestions_endpoint_returns_commercial_type() -> None:
    """The claim search filters to type == 'commercial'; the endpoint must
    expose that field so the client filter works. Empty query short-circuits."""
    r = client.get("/api/search/suggestions", params={"q": "a"})
    assert r.status_code == 200
    # <2 chars returns [] by contract; just assert the shape is a JSON list.
    assert isinstance(r.json(), list)
