"""Home + calendar redesign (``home_redesign`` flag, dark rollout).

Verifies: the flag is OFF by default (old home served, instant rollback intact);
the ``?home_redesign=1`` preview override swaps in the v4 templates and sticks via
cookie; the redesigned /home and /calendar render the v4 structure from real data;
the view-model adapters behave; and both surfaces clear the same WCAG 2.1 AA
structural contract as every other page.
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi.testclient import TestClient

# Reuse the structural WCAG checker the rest of the lake suite runs.
from test_ada_compliance import _A11yChecker

from app.db.database import get_db
from app.home import redesign
from app.home.flags import home_redesign_enabled
from app.main import app


# ── flag plumbing ──────────────────────────────────────────────────────────────
def test_flag_off_by_default_serves_old_home() -> None:
    r = TestClient(app).get("/home")
    assert r.status_code == 200
    assert "/static/styles/lake_redesign.css" not in r.text
    assert "/static/styles/lake_home.css" in r.text


def test_query_override_serves_redesign_and_sets_cookie() -> None:
    c = TestClient(app)
    r = c.get("/home?home_redesign=1")
    assert r.status_code == 200
    assert "/static/styles/lake_redesign.css" in r.text
    assert 'data-theme="lake"' in r.text
    # the preview override is persisted so navigation stays in the redesign
    assert "home_redesign" in r.cookies or "home_redesign" in r.headers.get("set-cookie", "")
    # cookie now sticks the redesign without the param
    assert "/static/styles/lake_redesign.css" in c.get("/home").text


def test_query_override_off_forces_old_even_with_cookie() -> None:
    c = TestClient(app)
    c.get("/home?home_redesign=1")  # set cookie
    assert "/static/styles/lake_redesign.css" not in c.get("/home?home_redesign=0").text


def test_flag_resolution_orders(monkeypatch) -> None:
    class _Req:
        def __init__(self, qp: dict[str, str], cookies: dict[str, str]):
            self.query_params = qp
            self.cookies = cookies

    monkeypatch.delenv("HOME_REDESIGN", raising=False)
    assert home_redesign_enabled(_Req({}, {})) is False  # type: ignore[arg-type]
    assert home_redesign_enabled(_Req({"home_redesign": "1"}, {})) is True  # type: ignore[arg-type]
    assert home_redesign_enabled(_Req({"home_redesign": "0"}, {"home_redesign": "1"})) is False  # type: ignore[arg-type]
    assert home_redesign_enabled(_Req({}, {"home_redesign": "1"})) is True  # type: ignore[arg-type]
    monkeypatch.setenv("HOME_REDESIGN", "1")
    assert home_redesign_enabled(_Req({}, {})) is True  # type: ignore[arg-type]


# ── redesigned home render ──────────────────────────────────────────────────────
def _home() -> str:
    return TestClient(app).get("/home?home_redesign=1").text


def test_home_redesign_structure() -> None:
    b = _home()
    assert b.count("<h1") == 1  # exactly one h1 (the feed heading)
    assert 'role="search"' in b  # hero search
    assert 'class="daystrip' in b  # one-week date strip
    assert 'class="calbtn"' in b  # Calendar button
    assert 'class="counts' in b  # count overview rail
    assert 'id="jump"' in b  # jump-to-category dropdown
    assert "/static/js/lake_redesign.js" in b  # progressive-enhancement layer
    # buyable ad placeholder, never a fake business
    assert "Ad space · Available" in b or "Sponsored" in b


def test_home_redesign_conditions_bar_with_seeded_data() -> None:
    """With live conditions + gas, the 5-tile bar + gas expander render (the bar
    is honestly omitted only when there is no data at all)."""
    from app.conditions.cache import upsert_source
    from app.conditions.constants import (
        SOURCE_GAS,
        SOURCE_NWS_CURRENT,
        SOURCE_NWS_FORECAST,
        SOURCE_OPENUV,
    )

    db = next(get_db())
    try:
        upsert_source(db, SOURCE_NWS_CURRENT, {"temperature_f": 104, "wind_speed_mph": 12})
        upsert_source(db, SOURCE_OPENUV, {"uv_index": 11})
        upsert_source(db, SOURCE_NWS_FORECAST, {"short_forecast": "Sunny"})
        upsert_source(
            db,
            SOURCE_GAS,
            {"cheapest": [{"name": "Circle K", "address": "Hwy 95", "prices": {"regular": 3.79}}]},
        )
        db.commit()
    finally:
        db.close()

    b = _home()
    assert 'class="cond"' in b  # conditions bar present
    assert 'id="gasPanel"' in b  # gas top-5 expander
    assert "$3.79" in b  # cheapest gas figure
    assert ">104°<" in b or "104°" in b  # temp tile, clean single value


def test_home_redesign_no_emoji_in_conditions() -> None:
    # conditions use the inline SVG icon set, not emoji
    b = _home()
    assert "⛽" not in b


def test_home_redesign_a11y() -> None:
    checker = _A11yChecker()
    checker.feed(_home())
    issues = checker.finish()
    assert not issues, f"A11y issues on redesigned /home: {issues}"


# ── redesigned calendar render ──────────────────────────────────────────────────
def _cal(qs: str = "") -> str:
    return TestClient(app).get(f"/calendar?home_redesign=1{qs}").text


def test_calendar_redesign_structure() -> None:
    b = _cal()
    assert "/static/styles/lake_redesign.css" in b
    assert 'class="calmonth"' in b  # month grid
    assert 'class="caldow"' in b  # weekday header row
    assert 'class="calback"' in b  # back-to-feed link
    # day cells are real links (no-JS fallback)
    assert "/calendar?cal=" in b


def test_calendar_redesign_month_nav() -> None:
    b = _cal("&cal=2026-07")
    assert "July 2026" in b


def test_calendar_redesign_a11y() -> None:
    checker = _A11yChecker()
    checker.feed(_cal())
    issues = checker.finish()
    assert not issues, f"A11y issues on redesigned /calendar: {issues}"


# ── view-model adapters (pure helpers + DB-backed shape) ────────────────────────
def test_uv_color_scale() -> None:
    assert redesign.uv_color(1) == "#2c7551"
    assert redesign.uv_color(4) == "#9a8a00"
    assert redesign.uv_color(7) == "#b5611f"
    assert redesign.uv_color(9) == "#b4452f"
    assert redesign.uv_color(11) == "#8a4fb8"


def test_blurb_first_sentence_and_cap() -> None:
    assert redesign._blurb(None) is None
    assert redesign._blurb("   ") is None
    out = redesign._blurb("Three days of music and food trucks. And more details here.")
    assert out == "Three days of music and food trucks."
    long = redesign._blurb("x" * 400)
    assert long is not None and len(long) <= 150


def test_first_hour_parses_clock() -> None:
    assert redesign._first_hour("8:30 AM") == 8.5
    assert redesign._first_hour("7:00 PM") == 19.0
    assert redesign._first_hour("All day") is None


def test_conditions_and_feed_shape_on_seeded_db() -> None:
    db = next(get_db())
    try:
        tiles = redesign.conditions_tiles(db, now=datetime(2026, 6, 25, 12, 0))
        assert isinstance(tiles, list)
        for t in tiles:
            assert {"key", "icon", "label", "value", "is_gas"} <= set(t)
        feed = redesign.feed_view_model(db, day=date(2026, 6, 25))
        assert {"buckets", "movie_bucket", "total"} <= set(feed)
        assert feed["total"] == sum(b["count"] for b in feed["buckets"]) + (
            feed["movie_bucket"]["count"] if feed["movie_bucket"] else 0
        )
        cal = redesign.calendar_month_view(db, year=2026, month=6, today=date(2026, 6, 25))
        assert cal["title"] == "June 2026"
        assert len(cal["weeks"]) >= 4
    finally:
        db.close()
