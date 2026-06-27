"""Universal Sonics class-schedule scraper — parse/validate (no network, no LLM).

The live LLM call is injected via ``raw_text`` (a recorded reply) exactly like
the vision-calendar tests, so these run offline and spend nothing. The HTML
fixture is a representative slice of the real ClassScheduleDeluxe grid.
"""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path

from app.contrib.universal_sonics import (
    call_llm,
    extract_rows,
    schedule_block,
    validate_rows,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "universal_sonics" / "schedule.html"

# A recorded model reply for the fixture. It includes one competitive row the
# model FAILED to drop ("Sonics Junior Commanders**") so the validator's
# belt-and-suspenders filter is exercised.
_RECORDED = json.dumps({"classes": [
    {"day": "Monday", "start_time": "15:00", "end_time": "16:15",
     "name": "Firecrackers Gymnastics", "age": None,
     "source_line": "3:00pm-4:15pm-Firecrackers Gymnastics *"},
    {"day": "Monday", "start_time": "16:00", "end_time": "17:00",
     "name": "Recreational Gymnastics", "age": "ages 5yr-9yr",
     "source_line": "4:00pm-5:00pm Recreational Gymnastics (ages 5yr-9yr)"},
    {"day": "Monday", "start_time": "16:00", "end_time": "17:30",
     "name": "Dynamites Gymnastics", "age": None,
     "source_line": "4:00pm-5:30pm-Dynamites Gymnastics *"},
    {"day": "Tuesday", "start_time": "15:30", "end_time": "16:30",
     "name": "Boys Athletics", "age": "Ages 5yrs-10yrs",
     "source_line": "3:30pm-4:30pm-Boys Athletics (Ages 5yrs-10yrs)"},
    {"day": "Tuesday", "start_time": "16:30", "end_time": "17:15",
     "name": "Tiny Tumblers", "age": "Ages 3yrs-4yrs",
     "source_line": "4:30pm-5:15pm- Tiny Tumblers (Ages 3yrs-4yrs)"},
    {"day": "Tuesday", "start_time": "17:00", "end_time": "19:00",
     "name": "Sonics Junior Commanders", "age": None,
     "source_line": "5:00pm-7:00pm-Sonics Junior Commanders**"},
]})


def test_schedule_block_drops_chrome_and_starts_at_weekday() -> None:
    block = schedule_block(_FIXTURE.read_text(encoding="utf-8"))
    assert block.startswith("Monday")
    assert "Member Login" not in block  # nav chrome dropped
    assert "nav tracking" not in block  # <script> dropped
    assert "Firecrackers Gymnastics" in block and "Tuesday" in block


def test_extract_rows_keeps_rec_drops_competitive() -> None:
    rows = extract_rows("(unused — raw_text injected)", raw_text=_RECORDED)
    names = [r.name for r in rows]
    # The ** competitive row is gone; the 5 recreational rows remain.
    assert "Sonics Junior Commanders" not in names
    assert len(rows) == 5
    assert all("**" not in r.source_line for r in rows)


def test_extract_rows_field_parsing() -> None:
    rows = {(r.name, r.weekday): r for r in extract_rows("x", raw_text=_RECORDED)}
    fire = rows[("Firecrackers Gymnastics", 0)]  # Monday
    assert fire.start_time == time(15, 0) and fire.end_time == time(16, 15)
    boys = rows[("Boys Athletics", 1)]  # Tuesday
    assert boys.age == "Ages 5yrs-10yrs"


def test_validate_drops_competitive_and_malformed() -> None:
    raw = [
        {"day": "Monday", "start_time": "15:00", "name": "Firecrackers", "source_line": "ok *"},
        {"day": "Monday", "start_time": "16:00", "name": "Team", "source_line": "Sonics X**"},
        {"day": "Funday", "start_time": "15:00", "name": "Bad day", "source_line": "x"},
        {"day": "Monday", "start_time": "nope", "name": "Bad time", "source_line": "x"},
        {"day": "Monday", "start_time": "15:00", "name": "", "source_line": "x"},
    ]
    rows = validate_rows(raw)
    assert [r.name for r in rows] == ["Firecrackers"]


def test_no_backend_returns_empty() -> None:
    # openai_symbol=None => no client => "" => no rows (graceful no-key path).
    assert call_llm("Monday 3pm Firecrackers", openai_symbol=None) == ""
    assert extract_rows("Monday 3pm Firecrackers", raw_text="") == []
