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


def test_only_styleguide_still_extends_base_lake() -> None:
    """PR-1 acceptance: zero app templates extend base_lake except the internal
    styleguide gallery (removed in PR-2 with base_lake + lake.css)."""
    offenders = []
    for tpl in _TEMPLATES.glob("*.html"):
        if 'extends "base_lake.html"' in tpl.read_text(encoding="utf-8"):
            offenders.append(tpl.name)
    assert offenders == ["lake_styleguide.html"], offenders


def test_public_last_pages_wear_v4_shell() -> None:
    """The migrated public surfaces render on the standalone v4 shell (its own
    lake_redesign.css), never the old base_lake reskin (data-redesign flag)."""
    with TestClient(app) as client:
        for path in ("/today", "/feedback", "/portal/claim", "/search", "/map"):
            html = client.get(path, follow_redirects=True).text
            assert "/static/styles/lake_redesign.css" in html, path
            # None of the deleted-in-PR-2 bespoke sheets are linked anymore.
            for dead in ("lake_conditions.css", "lake_account.css", "lake_portal.css",
                         "lake_editorial.css", "lake_landing.css", "lake_search.css",
                         "lake_map.css", "lake_group.css", "lake_error.css"):
                assert dead not in html, f"{path} still links {dead}"


def test_404_is_base_plain_v4() -> None:
    r = TestClient(app).get("/no-such-page-v46-xyz")
    assert r.status_code == 404
    assert "/static/styles/lake_redesign.css" in r.text
    assert 'class="errx"' in r.text
    assert 'href="/today"' in r.text  # Today link (Pre-answered 2)
    assert "base_lake" not in r.text
