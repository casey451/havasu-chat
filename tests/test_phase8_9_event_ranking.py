from __future__ import annotations

import unittest

from app.core.event_recurrence import event_text_blob, is_recurring_heuristic


class Phase89RecurrenceHeuristicTests(unittest.TestCase):
    def test_every_saturday_in_text_is_recurring(self) -> None:
        blob = event_text_blob("Yoga in the Park every Saturday", "morning class", [])
        self.assertTrue(is_recurring_heuristic(blob))

    def test_one_time_festival_is_not_recurring(self) -> None:
        blob = event_text_blob(
            "Desert Storm Poker Run 2026",
            "one-day speedboat event on the lake; tickets online.",
            ["racing", "fundraiser"],
        )
        self.assertFalse(is_recurring_heuristic(blob))


if __name__ == "__main__":
    unittest.main()
