"""
Parser tests for ``app.contrib.lhcaz_aquatic``.

Fixture: ``tests/fixtures/lhcaz_aquatic/schedule.html`` — a structural
slice of the live page covering one full day (Thursday May 7), one
partially-closed day (Saturday May 9), one fully-closed day (Sunday
May 10), and one day with a one-off class (Wednesday May 27 — Tai Chi).
"""

from __future__ import annotations

import unittest
from datetime import date, time
from pathlib import Path

from app.contrib.lhcaz_aquatic import (
    AquaticSlot,
    filter_for_chat,
    parse_schedule_html,
)


FIXTURE = Path(__file__).parent / "fixtures" / "lhcaz_aquatic" / "schedule.html"


def _load(today: date = date(2026, 5, 7)) -> list[AquaticSlot]:
    return parse_schedule_html(FIXTURE.read_text(encoding="utf-8"), today=today)


class ParseScheduleHtmlTests(unittest.TestCase):
    def test_total_slot_count(self) -> None:
        slots = _load()
        # Thu(8) + Sat(3) + Sun(1) + Wed(9) = 21
        self.assertEqual(len(slots), 21)

    def test_thursday_has_lap_swim(self) -> None:
        slots = _load()
        thu = [s for s in slots if s.day_name == "THURSDAY"]
        lap = next(s for s in thu if s.title == "Lap Swim" and s.start_time == time(5, 0))
        self.assertEqual(lap.slot_date, date(2026, 5, 7))
        self.assertEqual(lap.class_type, "lap_swim")
        self.assertEqual(lap.end_time, time(7, 45))
        self.assertEqual(lap.duration_minutes, 120)
        self.assertTrue(lap.is_public)

    def test_pool_closed_marked_not_public(self) -> None:
        slots = _load()
        closed = [s for s in slots if s.class_type == "pool_closed"]
        self.assertGreater(len(closed), 0)
        self.assertTrue(all(not s.is_public for s in closed))

    def test_private_practice_marked_not_public(self) -> None:
        slots = _load()
        private = [s for s in slots if s.class_type == "private_practice"]
        self.assertGreater(len(private), 0)
        self.assertTrue(all(not s.is_public for s in private))
        # And every one is the Stingrays line
        self.assertTrue(all("Stingrays" in s.title or "Stringrays" in s.title for s in private))

    def test_sunday_all_day_pool_closed(self) -> None:
        slots = _load()
        sunday = [s for s in slots if s.day_name == "SUNDAY"]
        self.assertEqual(len(sunday), 1)
        s = sunday[0]
        self.assertEqual(s.class_type, "pool_closed")
        self.assertTrue(s.all_day)
        self.assertIsNone(s.start_time)
        self.assertIsNone(s.end_time)
        self.assertIsNone(s.duration_minutes)

    def test_saturday_open_swim_window(self) -> None:
        slots = _load()
        sat = [s for s in slots if s.day_name == "SATURDAY"]
        open_swim = next(s for s in sat if s.class_type == "open_swim")
        self.assertEqual(open_swim.start_time, time(12, 0))
        self.assertEqual(open_swim.end_time, time(16, 0))
        self.assertEqual(open_swim.duration_minutes, 240)

    def test_end_of_day_token_handled(self) -> None:
        slots = _load()
        sat_pc = [s for s in slots if s.day_name == "SATURDAY" and s.class_type == "pool_closed"]
        late = next(s for s in sat_pc if s.start_time == time(16, 0))
        self.assertIsNone(late.end_time)
        self.assertFalse(late.all_day)

    def test_filter_for_chat_drops_closed_and_private(self) -> None:
        slots = _load()
        public = filter_for_chat(slots)
        types = {s.class_type for s in public}
        self.assertEqual(types, {"lap_swim", "exercise_class", "open_swim"})
        # Sunday (only pool_closed) should be entirely dropped.
        self.assertEqual([s for s in public if s.day_name == "SUNDAY"], [])

    def test_year_inference_rolls_forward(self) -> None:
        # If "today" is December 2026, MAY 7 must roll to 2027.
        slots = parse_schedule_html(
            FIXTURE.read_text(encoding="utf-8"),
            today=date(2026, 12, 1),
        )
        thu = [s for s in slots if s.day_name == "THURSDAY"][0]
        self.assertEqual(thu.slot_date, date(2027, 5, 7))

    def test_to_dict_is_json_safe(self) -> None:
        import json

        slots = _load()
        record = slots[0].to_dict()
        self.assertEqual(record["slot_date"], "2026-05-07")
        # Round-trip through JSON
        json.dumps(record)


if __name__ == "__main__":
    unittest.main()
