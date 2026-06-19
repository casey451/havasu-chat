"""Parser tests for the City Aquatic Center Open Gym pickleball schedule.

Fixture is the verbatim text layer of the City's June 2026 Open Gym PDF
(https://www.lhcaz.gov/DocumentCenter/View/788/Open-Gym-Schedule-PDF), so the
parser is exercised against the real document shape (Pickleball / Basketball /
"Closed For Event", single + double windows, ROUND ROBIN and GLOW variants).
"""

from datetime import date

from app.contrib.lhc_aquatic_pickleball import (
    AQUATIC_VENUE_NAME,
    parse_aquatic_open_gym,
)

JUNE_2026 = """Revised 5/29/2026
Sun Mon Tue Wed Thu Fri Sat
1
Closed
For
Event
2
Pickleball
9:00am — 12:00pm
12:30pm — 3:30pm
3
Pickleball
12:30pm — 3:30pm
4
Pickleball
9:00am — 12:00pm
12:30pm — 3:30pm
5
Pickleball
9:00am — 12:00pm
12:30pm — 3:30pm
6
Basketball
18 & up
12:30pm—3:30pm
7
Basketball
18 & up
12:30pm—
3:30pm
8
Closed
For
Event
9
Pickleball
9:00am — 12:00pm
12:30pm — 3:30pm
10
Pickleball
12:30pm — 3:30pm
11
Pickleball
ROUND ROBIN
(Must Pre-Register)
12:30pm — 3:30pm
12
Pickleball
9:00am — 12:00pm
12:30pm — 3:30pm
13
Basketball
18 & up
12:30pm—3:30pm
14
Basketball
18 & up
12:30pm—
3:30pm
15
Closed
For
Event
16
Pickleball
9:00am — 12:00pm
12:30pm — 3:30pm
17
Pickleball
12:30pm — 3:30pm
18
Closed
For
Event
19
GLOW Pickleball
12:30pm — 3:30pm
20
Closed
For
Event
21
Basketball
18 & up
12:30pm—
3:30pm
22
Closed
For
Event
23
Closed
For
Event
24
Pickleball
12:30pm — 3:30pm
25
Pickleball
ROUND ROBIN
(Must Pre-Register)
12:30pm — 3:30pm
26
Pickleball
12:30pm — 3:30pm
27
Basketball
18 & up
12:30pm—3:30pm
28
Basketball
18 & up
12:30pm—
3:30pm
29
Closed
For
Event
30
Closed
For
Event
Lake Havasu City Aquatic Center Open Gym June Schedule
Open Gym Schedule is for the Lake Havasu City Aquatic Center, Located at 100 Park Ave.
Cost is $3.00 per participant.
"""


def _by_date(specs):
    out: dict[date, list] = {}
    for s in specs:
        out.setdefault(s.date, []).append(s)
    return out


def test_parses_to_timed_specs_in_june_2026():
    specs = parse_aquatic_open_gym(JUNE_2026)
    assert specs, "expected pickleball specs"
    for s in specs:
        assert s.date.year == 2026 and s.date.month == 6
        assert s.all_day is False
        assert s.start_time and s.end_time
        assert s.location_name == AQUATIC_VENUE_NAME


def test_double_window_day():
    by = _by_date(parse_aquatic_open_gym(JUNE_2026))
    mon2 = sorted((s.start_time, s.end_time) for s in by[date(2026, 6, 2)])
    assert mon2 == [("09:00", "12:00"), ("12:30", "15:30")]


def test_single_window_day():
    by = _by_date(parse_aquatic_open_gym(JUNE_2026))
    tue3 = [(s.start_time, s.end_time) for s in by[date(2026, 6, 3)]]
    assert tue3 == [("12:30", "15:30")]


def test_basketball_and_closed_days_are_skipped():
    by = _by_date(parse_aquatic_open_gym(JUNE_2026))
    assert date(2026, 6, 1) not in by  # Closed For Event
    assert date(2026, 6, 6) not in by  # Basketball
    assert date(2026, 6, 20) not in by  # Closed


def test_glow_and_round_robin_labelled():
    by = _by_date(parse_aquatic_open_gym(JUNE_2026))
    assert "GLOW" in by[date(2026, 6, 19)][0].title
    assert "Round Robin" in by[date(2026, 6, 11)][0].title
    # plain open play keeps the open-play title
    assert "Open Play" in by[date(2026, 6, 16)][0].title


def test_empty_on_unparseable_header():
    assert parse_aquatic_open_gym("no header here") == []
