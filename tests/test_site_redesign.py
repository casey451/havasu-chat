"""Sitewide v4 reskin — baked into the base layout (flag collapsed 2026-07-02).

Every page extending ``base_lake.html`` carries ``data-redesign="1"`` on <html>
plus the scoped ``lake_redesign_site.css`` link directly in the template — the
HomeRedesignSkinMiddleware that used to buffer and string-rewrite every HTML
response is gone. The standalone v4 home/calendar (base_redesign, their own
lake_redesign.css) are not double-skinned. Reskinned pages must still clear the
structural WCAG 2.1 AA contract.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_ada_compliance import _A11yChecker

from app.main import app

# /events-ui (v4.5 PR-1) and the /categories directory (v4.5 PR-4) migrated to the
# standalone base_redesign shell — they no longer use the base_lake reskin these
# assertions check; their own v4 shell is tested below + in the directory tests.
_INNER = ["/about", "/help", "/contact"]

# Pages fully on the standalone v4 shell (base_redesign → its own lake_redesign.css,
# never the base_lake reskin sheet).
_V4_STANDALONE = ["/home", "/categories"]


@pytest.mark.parametrize("url", _INNER)
def test_reskin_is_baked_into_base_layout(url: str) -> None:
    b = TestClient(app).get(url).text
    assert 'data-redesign="1"' in b
    assert "/static/styles/lake_redesign_site.css" in b
    # the shared Lake CSS is still present (overrides layer on top of it)
    assert "/static/styles/lake.css" in b


def test_reskin_needs_no_flag_and_sets_no_cookie() -> None:
    r = TestClient(app).get("/about")
    assert 'data-redesign="1"' in r.text
    assert "home_redesign" not in (r.headers.get("set-cookie") or "")


@pytest.mark.parametrize("url", _V4_STANDALONE)
def test_standalone_v4_not_double_skinned(url: str) -> None:
    b = TestClient(app).get(url, follow_redirects=True).text
    assert "/static/styles/lake_redesign.css" in b  # its own v4 sheet
    assert "/static/styles/lake_redesign_site.css" not in b  # not double-linked
    assert "data-redesign" not in b  # not the base_lake reskin path


@pytest.mark.parametrize("url", ["/about"])
def test_reskinned_pages_a11y(url: str) -> None:
    checker = _A11yChecker()
    checker.feed(TestClient(app).get(url).text)
    issues = checker.finish()
    assert not issues, f"A11y issues on reskinned {url}: {issues}"
