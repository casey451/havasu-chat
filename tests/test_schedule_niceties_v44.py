"""v4.4 PR-7 — schedule niceties: day dots, section previews, places pills (Δ4/6/7)."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.home import redesign, sandstone
from app.home.activity import HEADLINER_DATES, activity_dots, strip_activity
from app.main import app

# ── date-strip activity (§2.3 / §6.4) ───────────────────────────────────────


def test_activity_dot_thresholds() -> None:
    assert activity_dots(0) == 0
    assert activity_dots(1) == 1
    assert activity_dots(19) == 1
    assert activity_dots(20) == 2
    assert activity_dots(49) == 2
    assert activity_dots(50) == 3
    assert activity_dots(240) == 3


def test_strip_activity_dots_vs_headliner_spark() -> None:
    quiet = strip_activity(25, date(2026, 8, 3))
    assert quiet["spark"] is False and quiet["dots"] == 2 and quiet["title"] is None
    hd = date(2026, 7, 4)
    assert hd.isoformat() in HEADLINER_DATES
    spark = strip_activity(99, hd)  # spark REPLACES dots regardless of count
    assert spark["spark"] is True and spark["dots"] == 0
    assert spark["title"] == HEADLINER_DATES[hd.isoformat()]


def test_week_strip_cards_carry_activity_and_weekend() -> None:
    with SessionLocal() as db:
        strip = sandstone.week_strip(db, today=date(2026, 7, 1))
    days = strip["days"]
    assert days, "week strip should have day cards"
    for card in days:
        assert "act" in card and isinstance(card["act"], dict)
        assert "dots" in card["act"] and "spark" in card["act"]
        assert "is_weekend" in card
    # July 4 falls in the window and is a configured headliner -> spark.
    jul4 = next((c for c in days if c["iso"] == "2026-07-04"), None)
    assert jul4 is not None and jul4["act"]["spark"] is True


# ── closed-section preview (§6.2) ────────────────────────────────────────────


def test_section_preview_rows_from_real_rows_capped_at_three() -> None:
    section = {
        "key": "events", "count": 5,
        "rows": [
            {"title": "Farmers Market", "time_label": "9:00 AM"},
            {"title": "Sunset Cruise", "time_label": "6:30 PM"},
            {"title": "Trivia Night", "time_label": "TBD start"},
            {"title": "Late Show", "time_label": "8 PM"},
        ],
    }
    pv = redesign._section_preview_rows(section)
    assert len(pv) == 3  # only the first three rows
    assert pv[0] == {"title": "Farmers Market", "time_short": "9:00 AM"}
    assert pv[2]["time_short"] == ""  # a TBD placeholder becomes a blank time
    assert "Late Show" not in [p["title"] for p in pv]


# ── places pills (§6.3) ──────────────────────────────────────────────────────


def test_home_renders_places_pills() -> None:
    with TestClient(app) as client:
        html = client.get("/home").text
    # Brass audience shortcuts, no count, linking the hubs.
    assert 'class="cpill places" href="/family"' in html
    assert 'class="cpill places" href="/seniors"' in html
    assert "For Kids" in html and "For Seniors" in html
