"""Chat ↔ calendar integration (Session AC-2)."""

from __future__ import annotations

import unittest

from app.core.intent import CALENDAR_VIEW, detect_intent, is_calendar_open_phrase


class CalendarIntentTests(unittest.TestCase):
    def test_calendar_phrases_detected(self) -> None:
        self.assertTrue(is_calendar_open_phrase("show me the calendar"))
        self.assertTrue(is_calendar_open_phrase("open calendar"))
        self.assertTrue(is_calendar_open_phrase("What's this month look like?"))
        self.assertTrue(is_calendar_open_phrase("show calendar"))

    def test_non_calendar_phrases_not_detected(self) -> None:
        self.assertFalse(is_calendar_open_phrase("what's on this weekend"))
        self.assertFalse(is_calendar_open_phrase("kids golf"))
        self.assertFalse(is_calendar_open_phrase("add an event"))
        self.assertFalse(is_calendar_open_phrase(""))

    def test_detect_intent_returns_calendar_view(self) -> None:
        self.assertEqual(detect_intent("show me the calendar"), CALENDAR_VIEW)
        self.assertEqual(detect_intent("Open calendar"), CALENDAR_VIEW)


if __name__ == "__main__":
    unittest.main()
