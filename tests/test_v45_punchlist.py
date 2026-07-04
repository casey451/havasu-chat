"""v4.5 PR-0 — two one-line copy bugs from the live QA sweep.

1. The home/calendar gas-panel footer prepended a literal "updated" to a label
   that already starts with "Updated" → "updated Updated today 1:23 PM".
2. The /news "Updated {date}." used the naive-UTC fetch date, so a Phoenix
   evening (UTC already the next day) showed tomorrow's date.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.conditions.cache import CacheReadResult
from app.main import app


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _gas_row() -> CacheReadResult:
    stations = [
        {"name": "A", "address": "1 St", "prices": {"regular": 3.5, "diesel": 4.8}},
        {"name": "B", "address": "2 St", "prices": {"regular": 3.2}},
    ]
    return CacheReadResult(
        data={"stations": stations}, fetched_at=_now(), ttl_seconds=86400, is_stale=False
    )


def test_gas_panel_footer_says_updated_once() -> None:
    with patch("app.home.redesign.read_source", return_value=_gas_row()):
        with TestClient(app) as client:
            html = client.get("/home").text
    # Isolate the panel footer link and count case-insensitive "updated".
    m = re.search(r'<a class="gpall"[^>]*>(.*?)</a>', html, re.DOTALL)
    assert m, "gas panel footer (.gpall) not found"
    footer = m.group(1)
    assert len(re.findall(r"updated", footer, re.IGNORECASE)) == 1, footer
    assert "updated Updated" not in footer


def test_news_updated_date_is_phoenix_local() -> None:
    # 2026-07-04 03:00 UTC == 2026-07-03 20:00 America/Phoenix -> "Jul 3".
    view = SimpleNamespace(
        items=[], is_stale=False, updated_at=datetime(2026, 7, 4, 3, 0, 0)
    )
    with patch("app.news.router.store.page_view", return_value=view):
        with TestClient(app) as client:
            html = client.get("/news").text
    assert "Updated Jul 3." in html
    assert "Updated Jul 4." not in html


def test_movies_page_wears_v4_shell() -> None:
    """PR-3: /movies renders in the v4 language (base_redesign), not base_lake."""
    with TestClient(app) as client:
        html = client.get("/movies").text
    # v4 shell stylesheet, no old desert/movies sheets.
    assert "/static/styles/lake_redesign.css" in html
    assert "desert_movies.css" not in html
    assert "base_lake" not in html
    # cond-tile strip is present on this discovery page.
    assert 'class="cond"' in html
    # serif page heading, single <h1>.
    assert html.count("<h1") == 1
    # zero emoji anywhere on the page (the forever guard).
    assert not any(
        0x1F000 <= ord(ch) <= 0x1FAFF or 0x2600 <= ord(ch) <= 0x27BF for ch in html
    )
    # the old drawn head-art scene is gone (§0 guardrail 3).
    assert "head-art" not in html


def test_directory_index_wears_v4_shell() -> None:
    """PR-4: the /categories directory index renders in the v4 language.

    (The listing/leaf/faceted pages need seeded taxonomy data — their v4 markup
    is covered against sample context in ``test_lake_directory.py``.)
    """
    with TestClient(app) as client:
        html = client.get("/categories").text
    assert "/static/styles/lake_redesign.css" in html
    assert "/static/styles/lake_directory.css" not in html
    assert "data-redesign" not in html  # the standalone v4 shell, not base_lake
    assert 'class="cond"' in html  # cond strip on the discovery page
    assert 'class="dirx"' in html  # v4 directory wrapper
    assert html.count("<h1") == 1
    # zero emoji — the rating star (on cards) is an inline SVG icon, not a ★ glyph.
    assert not any(
        0x1F000 <= ord(ch) <= 0x1FAFF or 0x2600 <= ord(ch) <= 0x27BF for ch in html
    )


def test_interior_pages_wear_v4_shell() -> None:
    """PR-5: the remaining interior pages render on the standalone v4 shell."""
    old_sheets = (
        "lake_editorial.css",
        "lake_account.css",
        "lake_landing.css",
        "lake_portal.css",
        "lake_profile.css",
        "desert_chat.css",
        "desert_home.css",
    )
    with TestClient(app) as client:
        for path in (
            "/about",
            "/help",
            "/contact",
            "/privacy",
            "/terms",
            "/seniors",
            "/login",
            "/sponsor",
            "/portal",
            "/family",
            "/night",
            "/chat",
        ):
            html = client.get(path, follow_redirects=True).text
            assert "/static/styles/lake_redesign.css" in html, path
            assert "data-redesign" not in html, f"{path} still on the base_lake reskin"
            assert not any(s in html for s in old_sheets), path
            assert html.count("<h1") == 1, path
            assert not any(
                0x1F000 <= ord(ch) <= 0x1FAFF or 0x2600 <= ord(ch) <= 0x27BF
                for ch in html
            ), f"{path} has emoji codepoints"


def test_old_shell_files_are_swept() -> None:
    """PR-7: the templates + stylesheets fully replaced by the v4 shell are gone
    (they'd only be dead weight / a re-skin regression risk if they crept back)."""
    import app as _app_pkg

    root = Path(_app_pkg.__file__).resolve().parent
    gone = [
        "templates/mode_sandstone.html",
        "templates/events_lake.html",
        "templates/movies_lake.html",
        "templates/_partials/movies_body.html",
        "static/styles/desert_home.css",
        "static/styles/desert_movies.css",
        "static/styles/lake_events.css",
        "static/styles/desert_chat.css",
        "static/styles/lake_directory.css",
        "static/styles/lake_profile.css",
        # v4.6 PR-2: the old base_lake shell + its whole CSS lineage are gone
        # (every page is on base_redesign / base_plain → lake_redesign.css).
        "templates/base_lake.html",
        "templates/lake_styleguide.html",
        "templates/components/lake_components.html",
        "home/lake_preview.py",
        "static/styles/site_chrome.css",
        "static/styles/lake.css",
        "static/styles/lake-components.css",
        "static/styles/lake_redesign_site.css",
        "static/styles/lake_conditions.css",
        "static/styles/lake_account.css",
        "static/styles/lake_editorial.css",
        "static/styles/lake_landing.css",
        "static/styles/lake_error.css",
        "static/styles/lake_search.css",
        "static/styles/lake_map.css",
        "static/styles/lake_group.css",
        "static/styles/desert_portal.css",
    ]
    still_here = [p for p in gone if (root / p).exists()]
    assert not still_here, f"old-shell files should be swept: {still_here}"
