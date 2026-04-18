"""Chat ↔ calendar integration (Session AC-2)."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.core.intent import CALENDAR_VIEW, detect_intent, is_calendar_open_phrase
from app.core.session import clear_session_state
from app.db.database import SessionLocal
from app.db.models import Event
from app.main import app


class CalendarIntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    def setUp(self) -> None:
        for sid in ("cal-open", "cal-month", "cal-neg"):
            clear_session_state(sid)
        with SessionLocal() as db:
            db.query(Event).delete()
            db.commit()

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

    def test_chat_endpoint_flags_open_calendar(self) -> None:
        r = self.__class__.client.post(
            "/chat",
            json={"session_id": "cal-open", "message": "show me the calendar"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["intent"], CALENDAR_VIEW)
        self.assertTrue(body.get("data", {}).get("open_calendar"))
        self.assertIn("calendar", body["response"].lower())

    def test_month_look_like_phrase_also_triggers(self) -> None:
        r = self.__class__.client.post(
            "/chat",
            json={"session_id": "cal-month", "message": "what's this month look like"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["intent"], CALENDAR_VIEW)
        self.assertTrue(body.get("data", {}).get("open_calendar"))

    def test_unrelated_message_does_not_trigger(self) -> None:
        r = self.__class__.client.post(
            "/chat",
            json={"session_id": "cal-neg", "message": "what's on this weekend"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertNotEqual(body["intent"], CALENDAR_VIEW)
        self.assertFalse(body.get("data", {}).get("open_calendar"))


if __name__ == "__main__":
    unittest.main()
