"""Parser tests for ``app.contrib.lhcaz_aquatic_pdf``.

Fixtures: ``tests/fixtures/lhcaz_aquatic_pdf/{exercise,swim}.pdf`` --
the canonical May 2026 schedule PDFs published by Lake Havasu City at
``/DocumentCenter/View/7325`` and ``/DocumentCenter/View/7326``.
Without committed fixtures the parser would be an HTTP-live test
only -- the same gap the original HTML scraper had per
``outputs/lhcaz_aquatic_pdf_rewrite_carry.md``.
"""

from __future__ import annotations

import json
import unittest
from datetime import date, time
from pathlib import Path

from app.contrib.lhcaz_aquatic import AquaticSlot, filter_for_chat
from app.contrib.lhcaz_aquatic_pdf import (
    EXERCISE_PDF_URL,
    SWIM_PDF_URL,
    parse_schedule_pdf,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "lhcaz_aquatic_pdf"
EXERCISE_FIXTURE = FIXTURE_DIR / "exercise.pdf"
SWIM_FIXTURE = FIXTURE_DIR / "swim.pdf"

# Pinned reference date: middle of the schedule month. The parser
# extracts the year from the PDF header directly, so ``today`` only
# affects fallback behavior -- changing this value should not change
# slot dates against the committed fixtures.
TODAY = date(2026, 5, 20)


def _load_exercise() -> list[AquaticSlot]:
    return parse_schedule_pdf(EXERCISE_FIXTURE.read_bytes(), today=TODAY)


def _load_swim() -> list[AquaticSlot]:
    return parse_schedule_pdf(SWIM_FIXTURE.read_bytes(), today=TODAY)


class ExercisePdfTests(unittest.TestCase):
    def test_total_slot_count(self) -> None:
        slots = _load_exercise()
        # 100 exercise classes across 21 weekdays in May 2026 (Mon-Fri,
        # minus Memorial Day 5/25) + 1 pool_closed entry for 5/25.
        self.assertEqual(len(slots), 101)

    def test_class_type_distribution(self) -> None:
        slots = _load_exercise()
        by_type: dict[str, int] = {}
        for s in slots:
            by_type[s.class_type] = by_type.get(s.class_type, 0) + 1
        self.assertEqual(by_type, {"exercise_class": 100, "pool_closed": 1})

    def test_monday_5_4_layout(self) -> None:
        """Spot-check a known Monday -- exact order, times, and titles."""
        slots = _load_exercise()
        mon = [s for s in slots if s.slot_date == date(2026, 5, 4)]
        self.assertEqual(len(mon), 5)
        self.assertEqual(mon[0].day_name, "MONDAY")
        self.assertEqual(mon[0].start_time, time(8, 0))
        self.assertEqual(mon[0].end_time, time(9, 0))
        self.assertEqual(mon[0].title, "Motion & Mobility Paula")
        self.assertEqual(mon[0].duration_minutes, 60)
        self.assertTrue(mon[0].is_public)

    def test_aqua_aerobics_title_intact(self) -> None:
        """Regression: ensure the time-range regex does NOT eat the leading
        'A' of 'Aqua Aerobics'. (Pre-fix, ``(am|pm|a|p)?`` greedily
        consumed the 'a' after ``8:15--9:15`` and produced
        ``'qua Aerobics Margie'``.)
        """
        slots = _load_exercise()
        titles = {s.title for s in slots}
        self.assertIn("Aqua Aerobics Margie", titles)
        self.assertNotIn("qua Aerobics Margie", titles)
        # And every Aqua Aerobics entry must keep the 'A'.
        for s in slots:
            if "qua Aerobics" in s.title and "Aqua" not in s.title:
                self.fail(f"Aqua title got truncated: {s.title!r}")

    def test_memorial_day_pool_closed(self) -> None:
        """5/25 (Memorial Day) is the only pool_closed entry on the
        exercise PDF -- a whole-day closure with no time.
        """
        slots = _load_exercise()
        closed = [s for s in slots if s.class_type == "pool_closed"]
        self.assertEqual(len(closed), 1)
        c = closed[0]
        self.assertEqual(c.slot_date, date(2026, 5, 25))
        self.assertTrue(c.all_day)
        self.assertIsNone(c.start_time)
        self.assertIsNone(c.end_time)
        self.assertIsNone(c.duration_minutes)
        self.assertFalse(c.is_public)

    def test_year_inference_from_header(self) -> None:
        """Year must come from the PDF header (``May 2026``), not from
        ``today``. Passing a today in a different year leaves the
        record year at 2026.
        """
        slots = parse_schedule_pdf(
            EXERCISE_FIXTURE.read_bytes(),
            today=date(2030, 1, 15),
        )
        years = {s.slot_date.year for s in slots}
        self.assertEqual(years, {2026})


class SwimPdfTests(unittest.TestCase):
    def test_total_slot_count(self) -> None:
        # 30 lap_swim + 5 open_swim + 6 pool_closed = 41 across May 2026.
        slots = _load_swim()
        self.assertEqual(len(slots), 41)

    def test_class_type_distribution(self) -> None:
        slots = _load_swim()
        by_type: dict[str, int] = {}
        for s in slots:
            by_type[s.class_type] = by_type.get(s.class_type, 0) + 1
        self.assertEqual(by_type, {"lap_swim": 30, "open_swim": 5, "pool_closed": 6})

    def test_friday_5_1_morning_lap_swim(self) -> None:
        """The 5-7:45a pattern (start lacks minutes, end has minute + 'a')
        must parse cleanly.
        """
        slots = _load_swim()
        fri = [s for s in slots if s.slot_date == date(2026, 5, 1)]
        self.assertEqual(len(fri), 1)
        lap = fri[0]
        self.assertEqual(lap.class_type, "lap_swim")
        self.assertEqual(lap.title, "Lap Swim")
        self.assertEqual(lap.start_time, time(5, 0))
        self.assertEqual(lap.end_time, time(7, 45))
        self.assertEqual(lap.duration_minutes, 165)
        self.assertEqual(lap.day_name, "FRIDAY")

    def test_saturday_5_2_free_family_swim(self) -> None:
        """5/2 has a multi-line cell: ``12-4p`` + ``Free Family Swim`` +
        sponsor metadata. The whole-hour PM time (``12-4p``) must parse
        as 12:00-16:00, and the multi-line title joins cleanly.
        """
        slots = _load_swim()
        sat = [s for s in slots if s.slot_date == date(2026, 5, 2)]
        self.assertEqual(len(sat), 1)
        s = sat[0]
        self.assertEqual(s.class_type, "open_swim")
        self.assertEqual(s.start_time, time(12, 0))
        self.assertEqual(s.end_time, time(16, 0))
        self.assertEqual(s.duration_minutes, 240)
        self.assertIn("Free Family Swim", s.title)

    def test_monday_5_4_noon_lap_swim_inference(self) -> None:
        """The ``12:15--2:00`` pattern (no am/pm marker, start hour 12)
        must infer PM via the noon heuristic, giving 12:15-14:00.
        """
        slots = _load_swim()
        mon = [s for s in slots if s.slot_date == date(2026, 5, 4)]
        # Two slots on Monday: 5-7:45a and 12:15--2:00.
        self.assertEqual(len(mon), 2)
        noon = next(s for s in mon if s.start_time == time(12, 15))
        self.assertEqual(noon.end_time, time(14, 0))
        self.assertEqual(noon.class_type, "lap_swim")
        self.assertEqual(noon.duration_minutes, 105)

    def test_open_swim_saturday_pattern(self) -> None:
        """Most Saturdays show ``12-4p Open Swim`` -- whole-hour PM."""
        slots = _load_swim()
        open_swim = [s for s in slots if s.class_type == "open_swim" and s.title == "Open Swim"]
        # 5/9, 5/16, 5/23, 5/30 -- four Saturdays.
        self.assertEqual(len(open_swim), 4)
        for s in open_swim:
            self.assertEqual(s.start_time, time(12, 0))
            self.assertEqual(s.end_time, time(16, 0))
            self.assertEqual(s.day_name, "SATURDAY")
            self.assertTrue(s.is_public)

    def test_pool_closed_not_public(self) -> None:
        slots = _load_swim()
        closed = [s for s in slots if s.class_type == "pool_closed"]
        # 6 Sundays/Memorial Day across the month.
        self.assertEqual(len(closed), 6)
        for s in closed:
            self.assertFalse(s.is_public)


class CrossCuttingTests(unittest.TestCase):
    def test_filter_for_chat_drops_closed(self) -> None:
        """The existing ``filter_for_chat`` helper should work on
        PDF-derived slots since the AquaticSlot dataclass is shared.
        """
        all_slots = _load_exercise() + _load_swim()
        public = filter_for_chat(all_slots)
        types = {s.class_type for s in public}
        self.assertEqual(types, {"lap_swim", "exercise_class", "open_swim"})
        self.assertEqual(len(public), len(all_slots) - 7)  # 1 + 6 pool_closed dropped

    def test_to_dict_is_json_safe(self) -> None:
        slot = _load_exercise()[0]
        rec = slot.to_dict()
        # Should round-trip cleanly through JSON.
        rt = json.loads(json.dumps(rec))
        self.assertEqual(rt["slot_date"], "2026-05-01")
        self.assertEqual(rt["start_time"], "08:00:00")
        self.assertEqual(rt["day_name"], "FRIDAY")
        self.assertIn("title", rt)

    def test_urls_point_at_documentcenter(self) -> None:
        """If the city moves the PDFs again, these constants must update
        in lockstep with the carry doc -- this test pins the current URLs.
        """
        self.assertIn("/DocumentCenter/View/7325", EXERCISE_PDF_URL)
        self.assertIn("/DocumentCenter/View/7326", SWIM_PDF_URL)
        self.assertTrue(EXERCISE_PDF_URL.startswith("https://"))
        self.assertTrue(SWIM_PDF_URL.startswith("https://"))


if __name__ == "__main__":
    unittest.main()
