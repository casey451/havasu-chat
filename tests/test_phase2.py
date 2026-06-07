from __future__ import annotations

import unittest
from calendar import monthrange
from datetime import date

from app.core.slots import extract_date_range
from app.core.timezone import now_lake_havasu


def _lhc_today() -> date:
    """P1-8 made extract_date_range anchor on the Lake Havasu (Phoenix) date.

    These tests previously compared against server-UTC ``date.today()``, which
    diverges from the Phoenix date between 00:00 and ~07:00 UTC — a nightly CI
    flake window (failed on unmodified main, 2026-06-07 00:04 UTC). Anchor the
    expectations on the same clock the code under test uses.
    """
    return now_lake_havasu().date()


class ExtractDateRangeTests(unittest.TestCase):
    def test_extract_date_range_this_week(self) -> None:
        dr = extract_date_range("what's on this week")
        self.assertIsNotNone(dr)
        assert dr is not None
        today = _lhc_today()
        self.assertEqual(dr["start"], today)
        offset = (dr["end"] - today).days
        self.assertGreaterEqual(offset, 0)
        self.assertLessEqual(offset, 6)
        self.assertEqual(dr["end"].weekday(), 6)  # Sunday

    def test_extract_date_range_next_week(self) -> None:
        dr = extract_date_range("anything going on next week")
        self.assertIsNotNone(dr)
        assert dr is not None
        today = _lhc_today()
        self.assertEqual(dr["start"].weekday(), 0)  # Monday
        self.assertGreater(dr["start"], today)
        self.assertLessEqual((dr["start"] - today).days, 7)
        self.assertEqual((dr["end"] - dr["start"]).days, 6)

    def test_extract_date_range_this_month(self) -> None:
        dr = extract_date_range("what's happening this month")
        self.assertIsNotNone(dr)
        assert dr is not None
        today = _lhc_today()
        self.assertEqual(dr["start"], today)
        last_day = monthrange(today.year, today.month)[1]
        self.assertEqual(dr["end"], date(today.year, today.month, last_day))

    def test_extract_date_range_next_month(self) -> None:
        dr = extract_date_range("events next month")
        self.assertIsNotNone(dr)
        assert dr is not None
        today = _lhc_today()
        next_month = today.month + 1 if today.month < 12 else 1
        next_year = today.year if today.month < 12 else today.year + 1
        last_day = monthrange(next_year, next_month)[1]
        self.assertEqual(dr["start"], date(next_year, next_month, 1))
        self.assertEqual(dr["end"], date(next_year, next_month, last_day))


if __name__ == "__main__":
    unittest.main()
