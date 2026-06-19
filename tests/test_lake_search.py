"""Lake Ink & Brass — /search keyword results page theme-select.

The concierge falls through to /search for descriptive queries, so /search must
follow the active theme (it was desert-only before). One check per theme, plus
the noindex/indexable split (results pages noindex, the bare form indexable).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

_NO_MATCH = "zzqq-no-such-business-xyz"


def test_search_lake_theme_select() -> None:
    b = TestClient(app).get(f"/search?q={_NO_MATCH}&theme=lake")
    assert b.status_code == 200
    assert "/static/styles/lake_search.css" in b.text
    assert 'data-theme="lake"' in b.text
    assert 'name="robots" content="noindex"' in b.text  # results page = noindex


def test_search_desert_is_default() -> None:
    # No theme param / cookie / THEME_DEFAULT in the test env → desert.
    b = TestClient(app).get(f"/search?q={_NO_MATCH}")
    assert b.status_code == 200
    assert "lake_search.css" not in b.text
    assert "desert_directory.css" in b.text


def test_search_lake_blank_query_indexable() -> None:
    b = TestClient(app).get("/search?theme=lake")
    assert b.status_code == 200
    assert "/static/styles/lake_search.css" in b.text
    assert 'name="robots" content="noindex"' not in b.text  # bare form stays indexable
