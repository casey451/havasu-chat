"""Sitewide v4 reskin (home_redesign) — the HomeRedesignSkinMiddleware.

When the flag is on, every HTML page (public + portal + admin) gets
``data-redesign="1"`` + the scoped ``lake_redesign_site.css`` injected, so the
whole site matches the v4 home. Flag off → byte-identical (no injection). The
standalone v4 home/calendar (their own lake_redesign.css) are skipped. Reskinned
pages must still clear the structural WCAG 2.1 AA contract.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_ada_compliance import _A11yChecker

from app.main import app

_INNER = ["/events-ui", "/categories", "/about", "/help", "/contact"]


def test_flag_off_no_injection() -> None:
    c = TestClient(app)
    for url in _INNER:
        b = c.get(url).text
        assert "lake_redesign_site.css" not in b
        assert 'data-redesign="1"' not in b


@pytest.mark.parametrize("url", _INNER)
def test_flag_on_injects_reskin(url: str) -> None:
    b = TestClient(app).get(f"{url}?home_redesign=1").text
    assert 'data-redesign="1"' in b
    assert "/static/styles/lake_redesign_site.css" in b
    # the shared Lake CSS is still present (overrides layer on top of it)
    assert "/static/styles/lake.css" in b


def test_standalone_v4_home_not_double_skinned() -> None:
    b = TestClient(app).get("/home?home_redesign=1").text
    assert "/static/styles/lake_redesign.css" in b  # its own v4 sheet
    assert "/static/styles/lake_redesign_site.css" not in b  # not double-injected


@pytest.mark.parametrize("url", ["/about?home_redesign=1", "/events-ui?home_redesign=1"])
def test_reskinned_pages_a11y(url: str) -> None:
    checker = _A11yChecker()
    checker.feed(TestClient(app).get(url).text)
    issues = checker.finish()
    assert not issues, f"A11y issues on reskinned {url}: {issues}"
