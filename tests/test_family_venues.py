"""Curated family-venue hours → "what's open for kids today" calendar rows.

Pins the honesty + shape contract of app.home.family_venues.open_today_rows so
the Kids & Family group can extend its rows directly: day-gated open hours, no
fabricated times, always-open rows sorting after timed events.

Weekday anchors (2026): Jun 15 = Mon, 16 = Tue, 17 = Wed, 18 = Thu, 19 = Fri,
20 = Sat, 21 = Sun.
"""

from __future__ import annotations

from datetime import date

from app.home.family_venues import (
    OPEN_VENUES,
    class_today_rows,
    open_today_rows,
)

_MON = date(2026, 6, 15)
_WED = date(2026, 6, 17)
_THU = date(2026, 6, 18)
_SUN = date(2026, 6, 21)


def _titles(rows) -> list[str]:
    return [r["title"] for r in rows]


def test_wednesday_includes_the_spot_with_bare_hours() -> None:
    rows = open_today_rows(_WED)
    spot = [r for r in rows if r["title"].startswith("The Spot")]
    assert len(spot) == 1
    # Bare hours range, no "Open" verb (the section heading already says open).
    assert spot[0]["time_label"] == "3–9 PM"
    assert spot[0]["url"].startswith("https://")
    assert spot[0]["recurring"] is False


def test_monday_omits_closed_spot_but_keeps_open_venues() -> None:
    rows = open_today_rows(_MON)
    titles = _titles(rows)
    # The Spot is closed Monday — never a fabricated "open" row.
    assert not any(t.startswith("The Spot") for t in titles)
    # Drop-in venues that ARE open Monday still appear.
    assert any("Altitude" in t for t in titles)
    assert any("Havasu Lanes" in t for t in titles)


def test_open_rows_show_bare_hours_not_a_verb_or_studio_classes() -> None:
    # Open-venue rows read as a bare hours range ("9 AM–5 PM") — no "Open" or
    # "Classes" verb — and the two class studios never appear here.
    for day in (_MON, _WED, _THU, _SUN):
        for r in open_today_rows(day):
            assert not r["time_label"].startswith(("Open ", "Classes "))
            assert r["time_label"].endswith((" AM", " PM"))
            assert "Universal Sonics" not in r["title"]
            assert "Black Belt" not in r["title"]


def test_havasu_lanes_shows_real_hours_and_the_neon_nights() -> None:
    # Friday: open noon–11 (bowling alley hours surfaced like any other venue),
    # with the Rock & Bowl neon nights called out in the subtitle.
    fri = open_today_rows(date(2026, 6, 19))
    lanes = next(r for r in fri if r["title"].startswith("Havasu Lanes"))
    assert lanes["time_label"] == "12–11 PM"
    assert "Rock & Bowl" in lanes["venue"]
    assert lanes["url"].startswith("https://www.havasulanesaz.com")


def test_studio_classes_file_under_their_youth_subsection() -> None:
    rows = class_today_rows(_WED)
    gym = [r for r in rows if r["subgroup"] == "Youth Gymnastics"]
    mart = [r for r in rows if r["subgroup"] == "Youth Martial Arts"]
    # Gymnastics studio → Youth Gymnastics; martial-arts studio → Youth Martial Arts.
    assert gym and all("Universal Sonics" in r["title"] for r in gym)
    assert mart and all("Black Belt Academy" in r["title"] for r in mart)
    # Real published time ranges — not an "Open"/"Classes" building-window label.
    sample = gym[0]
    assert "–" in sample["time_label"]
    assert not sample["time_label"].startswith(("Open ", "Classes "))
    assert sample["ongoing"] is False
    assert all(r["url"].startswith("http") for r in rows)


def test_studio_classes_are_day_gated_and_carry_ages() -> None:
    # Black Belt publishes no Sunday classes — none are fabricated.
    assert not [r for r in class_today_rows(_SUN) if "Black Belt" in r["title"]]
    # Thursday lists Tiny Tigers (ages 2–3) at the academy with its real time.
    thu = class_today_rows(_THU)
    tiny = [r for r in thu if r["title"].startswith("Tiny Tigers")]
    assert len(tiny) == 1
    assert tiny[0]["venue"] == "Ages 2–3"
    assert tiny[0]["time_label"] == "3:45–4:10 PM"


def test_rows_sort_after_timed_events_and_are_ordered() -> None:
    rows = open_today_rows(_SUN)
    assert rows, "Sunday should still have open family venues"
    # Always-open rows carry rank 2 so they sort after timed (0) and TBD (1).
    assert all(r["sort"][0] == 2 for r in rows)
    assert rows == sorted(rows, key=lambda r: r["sort"])


def test_every_open_venue_has_a_url_and_some_hours() -> None:
    # No curated FAMILY open-venue ships without a link or weekly hours (those
    # belong in DIRECTORY instead). Non-family funzone venues (billiards halls)
    # may lack confirmed hours — they surface in Things to Do with a "Hours vary"
    # label, never a fabricated time.
    for v in OPEN_VENUES:
        assert v.url.startswith("http")
        if v.family:
            assert v.hours, f"{v.name} has no hours — move it to DIRECTORY"
