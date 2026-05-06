"""Phase 8.5 — search & intent architecture rewrite (slots-only coverage).

Legacy deterministic intent + ``app.core.search`` pipeline tests were removed
at Slice 71 (Backlog #36 Option A).
"""

from __future__ import annotations

import unittest

from app.core.slots import (
    extract_activity_family,
    extract_audience,
    extract_date_range,
    merge_date_range,
)


class Phase85SlotTests(unittest.TestCase):
    def test_weekend_then_next_week_overwrites_date(self) -> None:
        d1 = extract_date_range("this weekend")
        d2 = extract_date_range("next week")
        assert d1 and d2
        merged = merge_date_range(d1, d2)
        self.assertEqual(merged, d2)

    def test_kids_weekend_one_message(self) -> None:
        msg = "kids stuff this weekend"
        self.assertIsNotNone(extract_date_range(msg))
        self.assertEqual(extract_audience(msg), "kids")

    def test_soccer_maps_sports(self) -> None:
        self.assertEqual(extract_activity_family("soccer clinic"), "sports")

    def test_first_friday_does_not_set_next_friday_date_range(self) -> None:
        self.assertIsNone(extract_date_range("first friday"))


if __name__ == "__main__":
    unittest.main()
