"""Home + calendar v4 (the collapsed ``home_redesign`` reskin).

The flag was collapsed 2026-07-02 (v4 permanently on in prod since ~06-23):
/home and /calendar serve the v4 templates unconditionally, with no
``?home_redesign=`` override, no cookie, and no legacy branch. Verifies the v4
structure renders from real data, the view-model adapters behave, and both
surfaces clear the same WCAG 2.1 AA structural contract as every other page.
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi.testclient import TestClient

# Reuse the structural WCAG checker the rest of the lake suite runs.
from test_ada_compliance import _A11yChecker

from app.db.database import get_db
from app.home import redesign
from app.main import app


# ── v4 is the only home ─────────────────────────────────────────────────────────
def test_home_serves_v4_unconditionally() -> None:
    r = TestClient(app).get("/home")
    assert r.status_code == 200
    assert "/static/styles/lake_redesign.css" in r.text
    assert 'data-theme="lake"' in r.text
    # No flag machinery left: the old preview override is inert, and no
    # home_redesign cookie is set.
    assert "home_redesign" not in (r.headers.get("set-cookie") or "")
    off = TestClient(app).get("/home?home_redesign=0")
    assert "/static/styles/lake_redesign.css" in off.text


# ── redesigned home render ──────────────────────────────────────────────────────
def _home() -> str:
    return TestClient(app).get("/home").text


def test_home_redesign_structure() -> None:
    b = _home()
    assert b.count("<h1") == 1  # exactly one h1 (the feed heading)
    assert 'role="search"' in b  # hero search
    assert 'class="daystrip' in b  # one-week date strip
    assert 'class="calbtn"' in b  # Calendar button
    # Session 1 declutter (2026-07-04): the count overview rail (class="counts")
    # and the "Jump to" dropdown (id="jump") were removed — they duplicated the
    # sections below. Their absence is asserted so they don't quietly return.
    assert 'class="counts' not in b
    assert 'id="jump"' not in b
    assert "/static/js/lake_redesign.js" in b  # progressive-enhancement layer
    # The marquee is a real sponsor ("Sponsored") or, when unsold, the P3 house
    # promo (free-listing claim + a small "Advertise" link) — never a fake business
    # and never a consumer-facing empty ad slot ("Your logo here").
    assert "For local businesses" in b or "Sponsored" in b
    assert "Your logo here" not in b


def test_home_redesign_emits_seo_jsonld() -> None:
    """F18: the v4 home carries Organization + WebSite (SearchAction) structured
    data — the old home had it, the v4 reskin had emitted none."""
    b = _home()
    assert b.count('type="application/ld+json"') >= 2
    assert '"@type": "Organization"' in b
    assert '"@type": "WebSite"' in b
    assert '"@type": "SearchAction"' in b
    # SearchAction points at the same /chat?q= the hero search submits to, with
    # the placeholder left literal for Google to fill.
    assert "/chat?q={search_term_string}" in b


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
        # v4.4 PR-1: the gas surfaces derive from the board's ``stations`` (the
        # single source the real pull always writes), not a bare ``cheapest`` list.
        upsert_source(
            db,
            SOURCE_GAS,
            {"stations": [{"name": "Circle K", "address": "Hwy 95", "prices": {"regular": 3.79}}]},
        )
        db.commit()
    finally:
        db.close()

    b = _home()
    assert 'class="cond"' in b  # conditions bar present
    assert 'id="gasPanel"' not in b  # M12: the per-page gas expander was removed
    assert '<a class="c gas" href="/gas"' in b  # gas chip now links to /gas
    assert "$3.79" in b  # cheapest gas figure (header chip)
    assert ">104°<" in b or "104°" in b  # temp tile, clean single value


def test_home_redesign_sections_are_native_details() -> None:
    # Accordion sections must work without JS — they are <details>/<summary>, and
    # never more than one carries the default `open` (the Events bucket only).
    import re

    b = _home()
    secs = re.findall(r"<details class=\"sec[^>]*", b)
    opens = [s for s in secs if " open" in s or s.rstrip().endswith("open")]
    assert len(opens) <= 1


def test_home_redesign_no_emoji_in_conditions() -> None:
    # conditions use the inline SVG icon set, not emoji
    b = _home()
    assert "⛽" not in b


def test_home_redesign_a11y() -> None:
    checker = _A11yChecker()
    checker.feed(_home())
    issues = checker.finish()
    assert not issues, f"A11y issues on redesigned /home: {issues}"


def test_home_redesign_has_header_landmark() -> None:
    """F17: the top bar is wrapped in a <header> banner landmark (was a bare div),
    alongside the existing <main> and <footer> landmarks."""
    b = _home()
    assert '<header class="head-stack">' in b
    assert "</header>" in b
    assert '<main id="main"' in b
    assert "<footer" in b


# ── redesigned calendar render ──────────────────────────────────────────────────
def _cal(qs: str = "") -> str:
    return TestClient(app).get(f"/calendar?{qs.lstrip('&')}").text


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
        # Parity refactor (Rule 0): the feed now returns the SAME nested section
        # tree /events-ui renders (sections → subgroups → rows), not chip buckets.
        feed = redesign.feed_view_model(db, day=date(2026, 6, 25))
        assert {"sections", "total"} <= set(feed)
        for s in feed["sections"]:
            assert {"key", "label", "count"} <= set(s)
        assert feed["total"] == sum(s["count"] for s in feed["sections"])
        cal = redesign.calendar_month_view(db, year=2026, month=6, today=date(2026, 6, 25))
        assert cal["title"] == "June 2026"
        assert len(cal["weeks"]) >= 4
    finally:
        db.close()


def test_calendar_month_view_blanks_past_days(monkeypatch) -> None:
    """Past days render empty on the /calendar month grid (Casey 2026-07-12: the
    calendar was showing every past day full of stale one-offs + backward-projected
    class rosters). Today and future days keep their chips/dots/count."""
    today = date(2027, 3, 15)

    def _cell(day: int) -> dict:
        return {
            "in_month": True,
            "day": day,
            "iso": date(2027, 3, day).isoformat(),
            "is_today": day == 15,
            "events": [{"title": f"Ev{day}", "time": "12 PM", "type": "events"}],
            "overflow": 2,
            "count": 3,
            "class_count": 4,
        }

    def _fake_grid(db, *, year, month, today):  # noqa: ARG001
        return {
            "weeks": [[_cell(5), _cell(15), _cell(25)]],
            "month_oneoff_total": 9,
            "month_class_total": 12,
        }

    monkeypatch.setattr(redesign.sandstone, "calendar_month", _fake_grid)
    db = next(get_db())
    try:
        cal = redesign.calendar_month_view(db, year=2027, month=3, today=today)
    finally:
        db.close()

    cells = {c["iso"]: c for wk in cal["weeks"] for c in wk if not c.get("empty")}
    past, now_, future = cells["2027-03-05"], cells["2027-03-15"], cells["2027-03-25"]

    # Past day: blanked (still rendered, greyed via is_past, but no events).
    assert past["is_past"] is True
    assert past["count"] == 0
    assert past["chips"] == [] and past["dots"] == [] and past["more"] == 0

    # Today + future: populated (3 one-off + 4 class = 7).
    assert now_["is_past"] is False and now_["count"] == 7
    assert future["is_past"] is False and future["count"] == 7
    assert any("Ev25" in ch["title"] for ch in future["chips"])
