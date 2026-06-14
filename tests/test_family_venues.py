"""Curated family-venue hours → "what's open for kids today" calendar rows.

Pins the honesty + shape contract of app.home.family_venues.open_today_rows so
the Kids & Family group can extend its rows directly: day-gated open hours, no
fabricated times, always-open rows sorting after timed events.

Weekday anchors (2026): Jun 15 = Mon, 16 = Tue, 17 = Wed, 18 = Thu, 19 = Fri,
20 = Sat, 21 = Sun.
"""

from __future__ import annotations

from datetime import date

from app.home.family_venues import OPEN_VENUES, open_today_rows

_MON = date(2026, 6, 15)
_WED = date(2026, 6, 17)
_SUN = date(2026, 6, 21)


def _titles(rows) -> list[str]:
    return [r["title"] for r in rows]


def test_wednesday_includes_the_spot_with_open_label() -> None:
    rows = open_today_rows(_WED)
    spot = [r for r in rows if r["title"].startswith("The Spot")]
    assert len(spot) == 1
    # Honest derived hours from the curated data (Wed 3–9).
    assert spot[0]["time_label"] == "Open 3–9 PM"
    assert spot[0]["url"].startswith("https://")
    assert spot[0]["recurring"] is False


def test_monday_omits_closed_spot_but_keeps_open_venues() -> None:
    rows = open_today_rows(_MON)
    titles = _titles(rows)
    # The Spot is closed Monday — never a fabricated "open" row.
    assert not any(t.startswith("The Spot") for t in titles)
    # Venues that ARE open Monday still appear.
    assert any("Altitude" in t for t in titles)
    assert any("Black Belt" in t for t in titles)


def test_studio_rows_use_classes_verb() -> None:
    rows = open_today_rows(_WED)
    sonics = next(r for r in rows if "Universal Sonics" in r["title"])
    assert sonics["time_label"].startswith("Classes ")


def test_rows_sort_after_timed_events_and_are_ordered() -> None:
    rows = open_today_rows(_SUN)
    assert rows, "Sunday should still have open family venues"
    # Always-open rows carry rank 2 so they sort after timed (0) and TBD (1).
    assert all(r["sort"][0] == 2 for r in rows)
    assert rows == sorted(rows, key=lambda r: r["sort"])


def test_every_open_venue_has_a_url_and_some_hours() -> None:
    # No curated open-venue ships without a link or without any weekly hours
    # (those belong in DIRECTORY instead).
    for v in OPEN_VENUES:
        assert v.url.startswith("http")
        assert v.hours, f"{v.name} has no hours — move it to DIRECTORY"
