"""Phase 9a — /category/events date chips + chronological sort."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.api.routes.category_pages import event_window_for_chip
from app.main import app


def test_events_config_has_when_chips() -> None:
    from app.api.routes.category_pages import category_page_config

    cfg = category_page_config("events")
    params = {c["param"] for c in cfg.operational_chips}
    assert "when" in params
    assert cfg.sort_default == "chronological"


def test_category_events_page_redirects_to_things_to_do() -> None:
    client = TestClient(app)
    r = client.get("/category/events", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/categories/things-to-do"


def test_category_events_when_today_query() -> None:
    client = TestClient(app)
    r = client.get("/category/events?when=today", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/categories/things-to-do?when=today"


def test_next_month_window() -> None:
    today = date(2026, 5, 23)
    start, end = event_window_for_chip("next-month", today=today)
    assert start.month == 6
    assert end.month == 6
