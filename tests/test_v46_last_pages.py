"""v4.6 PR-1 — the last pages migrated off base_lake onto the v4 shell.

/today, the account/portal/claim/login utility pages, /feedback, /search, /map,
the collection/event-permalink landings, the error pages, and the admin family
all left base_lake.html. After this, the ONLY template still extending base_lake
is the internal lake_styleguide gallery, which PR-2 deletes together with the old
shell + the lake.css component library it demos.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import app as app_pkg
from app.main import app

_TEMPLATES = Path(app_pkg.__file__).parent / "templates"


_STYLES = _TEMPLATES.parent / "static" / "styles"

# The whole base_lake shell + its CSS lineage, deleted in PR-2.
_DELETED = [
    _TEMPLATES / "base_lake.html",
    _STYLES / "site_chrome.css",
    _STYLES / "lake.css",
    _STYLES / "lake-components.css",
    _STYLES / "lake_redesign_site.css",
    _STYLES / "lake_conditions.css",
    _STYLES / "lake_account.css",
    _STYLES / "lake_editorial.css",
    _STYLES / "lake_landing.css",
    _STYLES / "lake_error.css",
    _STYLES / "lake_search.css",
    _STYLES / "lake_map.css",
    _STYLES / "lake_group.css",
    _STYLES / "desert_portal.css",
    # v4.6 follow-up: /contribute moved from a standalone inline page onto the v4
    # shell, so its bespoke sheet is gone too.
    _STYLES / "contribute.css",
]


def test_base_lake_and_its_css_lineage_are_deleted() -> None:
    """PR-2: base_lake.html + site_chrome.css + every stylesheet only they used
    are gone from disk — ONE shell remains (lake_redesign.css)."""
    present = [p.name for p in _DELETED if p.exists()]
    assert not present, f"should be deleted: {present}"


def test_zero_templates_extend_base_lake_or_link_deleted_sheets() -> None:
    """No app template extends base_lake or links any deleted stylesheet."""
    dead_links = {p.name for p in _DELETED if p.suffix == ".css"}
    offenders = []
    for tpl in _TEMPLATES.rglob("*.html"):
        body = tpl.read_text(encoding="utf-8")
        if 'extends "base_lake.html"' in body:
            offenders.append(f"{tpl.name}: extends base_lake")
        for css in dead_links:
            if f"/static/styles/{css}" in body:
                offenders.append(f"{tpl.name}: links {css}")
    assert not offenders, offenders


def test_public_last_pages_wear_v4_shell() -> None:
    """The migrated public surfaces render on the standalone v4 shell (its own
    lake_redesign.css), never the old base_lake reskin (data-redesign flag)."""
    with TestClient(app) as client:
        for path in ("/today", "/feedback", "/portal/claim", "/search", "/map", "/contribute"):
            html = client.get(path, follow_redirects=True).text
            assert "/static/styles/lake_redesign.css" in html, path
            # None of the deleted bespoke sheets are linked anymore.
            for dead in ("lake_conditions.css", "lake_account.css", "lake_portal.css",
                         "lake_editorial.css", "lake_landing.css", "lake_search.css",
                         "lake_map.css", "lake_group.css", "lake_error.css", "contribute.css"):
                assert dead not in html, f"{path} still links {dead}"


def test_404_is_base_plain_v4() -> None:
    r = TestClient(app).get("/no-such-page-v46-xyz")
    assert r.status_code == 404
    assert "/static/styles/lake_redesign.css" in r.text
    assert 'class="errx"' in r.text
    assert 'href="/today"' in r.text  # Today link (Pre-answered 2)
    assert "base_lake" not in r.text
