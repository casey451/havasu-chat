"""v4.5 PR-0 — two one-line copy bugs from the live QA sweep.

1. The home/calendar gas-panel footer prepended a literal "updated" to a label
   that already starts with "Updated" → "updated Updated today 1:23 PM".
2. The /news "Updated {date}." used the naive-UTC fetch date, so a Phoenix
   evening (UTC already the next day) showed tomorrow's date.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
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
