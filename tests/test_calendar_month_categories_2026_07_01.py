"""Month-calendar category fixes (2026-07-01 July audit).

The home-screen month calendar read as a mess: DB venue-hours rows ("Indoor
Golf Simulators") rendered as event pills, and venue specials published as
distinct dated one-off rows (Toptracer Family Night Golf on ~29 of 31 July
days, Cosmic Bowling, Glow in the Park, Junior Jump Time) claimed the two
visible pill slots on virtually every cell, drowning genuine one-offs. The
agenda under the grid captioned every venue-hours row "Event", and the
"learn" (Classes & Workshops) bucket fell through every category map to the
civic-gray fallback. Plus two taxonomy gaps the audit surfaced: "Dodgeball
USA" (a Parks & Rec sport) fell to Around Town, and the Senior Center's
generic "Exercise Class" mis-filed under Social, Music & Meals.
"""

from __future__ import annotations

from datetime import date, time

import app.home.sandstone as sandstone
from app.events.activity_taxonomy import (
    SENIOR_FITNESS_LABEL,
    classify_class_subgroup,
    classify_senior_subgroup,
)
from app.home import events_views, redesign


class _Ev:
    def __init__(
        self,
        title: str,
        location_name: str = "",
        tags: list[str] | None = None,
        start_time: time | None = None,
        recurring: bool = False,
    ) -> None:
        self.title = title
        self.location_name = location_name
        self.description = ""
        self.tags = tags or []
        self.start_time = start_time
        self.end_time = None
        self.featured = False
        self.is_recurring = recurring


def _month(monkeypatch, events_by_day: dict[date, list[_Ev]]) -> dict:
    monkeypatch.setattr(
        sandstone,
        "_live_events_by_day",
        lambda db, *, window_start, window_end: events_by_day,
    )
    monkeypatch.setattr(
        sandstone,
        "class_occurrences_in_window",
        lambda db, *, window_start, window_end, horizon_today=None: [],
    )
    return sandstone.calendar_month(db=None, year=2026, month=7, today=date(2026, 7, 1))


def _cell(month: dict, day: int) -> dict:
    return next(
        c
        for week in month["weeks"]
        for c in week
        if c.get("in_month") and c.get("day") == day
    )


# --- venue-hours rows never become month pills or counts ----------------------


def test_month_cells_drop_db_venue_hours_rows(monkeypatch) -> None:
    hours = _Ev(
        "Indoor Golf Simulators — Back Nine Golf",
        "Back Nine Golf",
        tags=["activity:golf", "facet:hours"],
    )
    market = _Ev("Farmers Market", "Main Street", start_time=time(8, 0))
    month = _month(monkeypatch, {date(2026, 7, 15): [hours, market]})
    cell = _cell(month, 15)
    titles = [p["title"] for p in cell["events"]]
    assert titles == ["Farmers Market"]
    # Not an event AND not a class: no leak into either count.
    assert cell["count"] == 1
    assert cell["class_count"] == 0
    assert month["month_oneoff_total"] == 1


# --- recurring-in-practice series sink below genuine one-offs -----------------


def test_month_series_rows_sink_below_genuine_oneoffs(monkeypatch) -> None:
    """A venue special repeating across the month (is_recurring=False on every
    dated row) no longer claims a visible slot ahead of a real one-off."""
    days = {}
    for d in (10, 11, 12):
        days.setdefault(date(2026, 7, d), []).append(
            _Ev(
                "Toptracer Range — Family Night Golf",
                "Iron Wolf Toptracer Range",
                tags=["activity:golf", "venue-kind:range"],
                start_time=time(17, 0),
            )
        )
    days[date(2026, 7, 11)].insert(
        0, _Ev("July After Hours Mixer", "Chamber", start_time=time(17, 0))
    )
    month = _month(monkeypatch, days)
    cell_11 = _cell(month, 11)
    # The genuine one-off wins the first visible slot; the series row follows.
    assert "Mixer" in cell_11["events"][0]["title"]
    assert cell_11["count"] == 2  # the series row still counts for its day
    # On a day with nothing else on, the series row still surfaces (honest).
    cell_10 = _cell(month, 10)
    assert any("Family Night Golf" in p["title"] for p in cell_10["events"])


def test_month_series_demotion_spares_special_tier(monkeypatch) -> None:
    """A real multi-day special (festival/derby/tournament) keeps its slot."""
    days: dict[date, list[_Ev]] = {}
    for d in (20, 21, 22):
        days.setdefault(date(2026, 7, d), []).append(
            _Ev("Havasu Fishing Derby", "London Bridge Beach", start_time=time(6, 0))
        )
    days[date(2026, 7, 21)].append(
        _Ev("Farmers Market", "Main Street", start_time=time(8, 0))
    )
    month = _month(monkeypatch, days)
    cell = _cell(month, 21)
    assert "Derby" in cell["events"][0]["title"]


def test_pill_sort_key_orders_series_after_oneoffs() -> None:
    oneoff = {"type": "community", "recurring": False, "series": False}
    series = {"type": "community", "recurring": False, "series": True}
    special_series = {"type": "special", "recurring": False, "series": True}
    recurring = {"type": "class", "recurring": True, "series": False}
    ranked = sorted([recurring, series, oneoff, special_series], key=sandstone._pill_sort_key)
    assert ranked == [special_series, oneoff, series, recurring]


# --- taxonomy gaps the July audit surfaced ------------------------------------


def test_dodgeball_types_as_sport_and_stays_in_fitness_group() -> None:
    assert classify_class_subgroup("Dodgeball USA") == "Sports & Racing"
    # The class-tier reroute to Around Town only fires for the untyped residue,
    # so a dodgeball program now stays under Fitness & Sports.
    assert events_views._occurrence_group_keys(
        "classes",
        title="Dodgeball USA",
        venue="Lake Havasu City Aquatic Center",
        activity=None,
        tags=["sports"],
        is_senior=False,
    ) == ["classes"]


def test_exercise_class_types_strength_and_senior_fitness() -> None:
    assert classify_class_subgroup("Exercise Class") == "Strength & Cardio"
    # The Senior Center's generic exercise class files under Fitness & Movement,
    # not the Social/Meals fallback.
    assert classify_senior_subgroup("Exercise Class") == SENIOR_FITNESS_LABEL
    # The specific subgroups still win over the generic word: pool exercise
    # stays Aquatic fitness, gentle/arthritis classes stay Mind & Body.
    assert classify_class_subgroup("Water Exercise") == "Aquatic fitness"
    assert classify_class_subgroup("Arthritis Foundation Exercise") == "Mind & Body"


# --- agenda captions + the "learn" category maps ------------------------------


def test_agenda_labels_venue_hours_open_today_and_learn_workshop(monkeypatch) -> None:
    sections = [
        {
            "key": "events",
            "label": "Things to Do",
            "icon": "",
            "count": 3,
            "rows": [
                {
                    "time_label": "9 AM–5 PM",
                    "title": "Sunshine Indoor Play",
                    "url": "https://example.com",
                    "ongoing": True,
                },
                {
                    "time_label": "11 AM–11 PM",
                    "title": "Mr. Lucky's Billiards & Pub",
                    "url": "https://example.com",
                    "tags": ["activity:billiards", "facet:hours"],
                },
                {
                    "time_label": "5:30 PM",
                    "title": "Sip, Mingle & Shop",
                    "url": "/events/x",
                },
            ],
        },
        {
            "key": "learn",
            "label": "Classes & Workshops",
            "icon": "",
            "count": 1,
            "rows": [
                {
                    "time_label": "6 PM",
                    "title": "DIY Patriotic Champagne Bottle Workshop",
                    "url": "/events/y",
                }
            ],
        },
    ]
    monkeypatch.setattr(
        events_views,
        "calendar_day_view_model",
        lambda db, *, day, now=None: {"sections": sections, "total": 4},
    )
    agenda = redesign._agenda(None, date(2026, 7, 1))
    by_title = {r["title"]: r for r in agenda["rows"]}
    assert by_title["Sunshine Indoor Play"]["cat_label"] == "Open today"
    assert by_title["Mr. Lucky's Billiards & Pub"]["cat_label"] == "Open today"
    assert by_title["Sip, Mingle & Shop"]["cat_label"] == "Event"
    workshop = by_title["DIY Patriotic Champagne Bottle Workshop"]
    assert workshop["cat_label"] == "Workshop"
    # learn wears the palette's --c-classes accent, not the civic fallback.
    assert workshop["color"] == "var(--c-classes)"
