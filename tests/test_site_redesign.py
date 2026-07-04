"""Sitewide v4 shell — the standalone base_redesign layout.

v4.6 PR-1 moved the last discovery/utility pages (/today, /account, /contribute,
/feedback, /portal/claim, errors) off the old base_lake reskin; PR-2 deletes
base_lake.html entirely. So there is no base_lake reskin sentinel left — every
public page rides the standalone v4 shell (base_redesign → its own
lake_redesign.css), which must still clear the structural WCAG 2.1 AA contract.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_ada_compliance import _A11yChecker

from app.main import app

# Pages fully on the standalone v4 shell (base_redesign → its own lake_redesign.css,
# never the deleted base_lake reskin sheet). /today joined this set in v4.6 PR-1.
_V4_STANDALONE = ["/home", "/categories", "/about", "/help", "/contact", "/sponsor", "/today"]


@pytest.mark.parametrize("url", _V4_STANDALONE)
def test_standalone_v4_shell(url: str) -> None:
    b = TestClient(app).get(url, follow_redirects=True).text
    assert "/static/styles/lake_redesign.css" in b  # its own v4 sheet
    # The deleted base_lake reskin path is gone: no data-redesign flag, no
    # lake_redesign_site.css override layer.
    assert "/static/styles/lake_redesign_site.css" not in b
    assert "data-redesign" not in b


@pytest.mark.parametrize("url", ["/today"])
def test_reskinned_pages_a11y(url: str) -> None:
    checker = _A11yChecker()
    checker.feed(TestClient(app).get(url).text)
    issues = checker.finish()
    assert not issues, f"A11y issues on {url}: {issues}"
