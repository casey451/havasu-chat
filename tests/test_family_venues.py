"""Curated family-venue hours → "what's open for kids today" calendar rows.

Pins the honesty + shape contract of app.home.family_venues.open_today_rows so
the Kids & Family group can extend its rows directly: day-gated open hours, no
fabricated times, always-open rows sorting after timed events.

Weekday anchors (2026): Jun 15 = Mon, 16 = Tue, 17 = Wed, 18 = Thu, 19 = Fri,
20 = Sat, 21 = Sun.
"""

from __future__ import annotations

from datetime import date, time

from app.home.family_venues import (
    HOURS_VARY_LABEL,
    OPEN_VENUES,
    FamilyVenue,
    _fmt_span,
    class_today_rows,
    funzone_hours_rows,
    open_today_rows,
)

_MON = date(2026, 6, 15)
_WED = date(2026, 6, 17)
_THU = date(2026, 6, 18)
_FRI = date(2026, 6, 19)
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


def test_havasu_lanes_hours_row_does_not_repeat_the_cosmic_night() -> None:
    # Friday: open noon–11 (bowling alley hours surfaced like any other venue).
    # The Rock & Bowl / Cosmic glow night is owned by the dated "Cosmic Bowling"
    # event series, so the hours-row subtitle must NOT re-advertise it — else the
    # glow night reads twice under Bowling (Casey, 2026-06-27).
    fri = open_today_rows(date(2026, 6, 19))
    lanes = next(r for r in fri if r["title"].startswith("Havasu Lanes"))
    # §6: noon-open span keeps the open meridiem ("12 PM–11 PM"), not "12–11 PM".
    assert lanes["time_label"] == "12 PM–11 PM"
    assert "Bumper lanes" in lanes["venue"]
    assert "Rock & Bowl" not in lanes["venue"]
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


def test_fmt_span_keeps_meridiem_for_noon_open() -> None:
    """§6: a noon-open span keeps the open meridiem ("12 PM–11 PM"), never the
    ambiguous "12–11 PM"; non-noon same-meridiem spans still collapse."""
    assert _fmt_span(time(12, 0), time(23, 0)) == "12 PM–11 PM"
    assert _fmt_span(time(12, 0), time(22, 0)) == "12 PM–10 PM"
    # Non-noon, same meridiem → drop the redundant first meridiem.
    assert _fmt_span(time(15, 0), time(21, 0)) == "3–9 PM"
    # Different meridiems → both shown.
    assert _fmt_span(time(9, 0), time(14, 0)) == "9 AM–2 PM"


def test_fmt_span_keeps_meridiem_for_midnight_close() -> None:
    """An 11am-to-midnight span keeps the close meridiem ("11 AM–12 AM"), never
    the ambiguous "11–12 AM" — the mirror of the noon-open guard (Lady Lee's
    Fri/Sat close at midnight; mirrors lhc_golf for Golf n' Brews)."""
    assert _fmt_span(time(11, 0), time(0, 0)) == "11 AM–12 AM"
    assert _fmt_span(time(9, 0), time(0, 0)) == "9 AM–12 AM"


def test_lady_lees_funzone_hours_show_real_window_not_hours_vary() -> None:
    """Part A: Lady Lee's now carries its verified weekly hours, so its Things-to-
    Do → Billiards hours row shows the REAL window per weekday instead of the
    "Hours vary" fallback (provider hours, curated like golf #601)."""
    def _lady(day: date) -> dict:
        return next(
            r for r in funzone_hours_rows(day) if r["title"] == "Lady Lee's Billiards Hall"
        )

    assert _lady(_MON)["time_label"] == "11 AM–10 PM"   # Mon–Thu 11–10
    assert _lady(_FRI)["time_label"] == "11 AM–12 AM"    # Fri/Sat close at midnight
    assert _lady(_SUN)["time_label"] == "11 AM–9 PM"     # Sun 11–9
    # Routed under Billiards (venue-kind tag) and read as a listing, not an event.
    assert _lady(_MON)["tags"] == ["activity:billiards", "facet:hours"]
    assert _lady(_MON)["ongoing"] is True
    # No funzone venue should read "Hours vary" any more — every one is curated.
    assert all(r["time_label"] != HOURS_VARY_LABEL for r in funzone_hours_rows(_MON))


def test_funzone_hours_unconfirmed_venue_reads_hours_vary() -> None:
    """Honest fallback: a funzone venue with NO confident weekly hours still
    reads "Hours vary" (never a fabricated time). ``venues`` is injected so the
    fallback branch stays covered even though every shipped venue now has hours."""
    unknown = FamilyVenue(
        name="Mystery Pool Hall",
        kind="Billiards hall",
        url="https://example.com/",
        venue_kind="billiards",
        family=False,
    )
    rows = funzone_hours_rows(_MON, venues=(unknown,))
    assert len(rows) == 1
    assert rows[0]["time_label"] == HOURS_VARY_LABEL
