from __future__ import annotations

import unittest
from calendar import monthrange
from datetime import date

from fastapi.testclient import TestClient

from app.core.session import clear_session_state, get_session
from app.core.slots import extract_date_range
from app.db.database import SessionLocal
from app.db.models import Event
from app.main import app


class Phase2ChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    def setUp(self) -> None:
        with SessionLocal() as db:
            db.query(Event).delete()
            db.commit()
        clear_session_state("phase2-add")
        clear_session_state("phase2-unclear")
        clear_session_state("phase2-no")

    def test_add_event_flow_end_to_end(self) -> None:
        first = self.__class__.client.post(
            "/chat",
            json={
                "session_id": "phase2-add",
                "message": (
                    "basketball camp Saturday at 9 at aquatic center "
                    "https://example.com/bcamp info 928-555-0100"
                ),
            },
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["intent"], "ADD_EVENT")
        self.assertIn("Sound right?", first.json()["response"])

        second = self.__class__.client.post(
            "/chat",
            json={"session_id": "phase2-add", "message": "yes"},
        )
        self.assertEqual(second.status_code, 200)
        self.assertIn("live", second.json()["response"].lower())

        with SessionLocal() as db:
            events = db.query(Event).all()
            self.assertTrue(any(e.title.startswith("Basketball Camp") for e in events))

    def test_gibberish_biases_to_search_then_asks_date(self) -> None:
        response = self.__class__.client.post(
            "/chat",
            json={"session_id": "phase2-unclear", "message": "quantum flux capacitor settings"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intent"], "SEARCH_EVENTS")
        body = response.json()["response"].lower()
        self.assertTrue(
            "nothing yet" in body or "tighten" in body or "when are you thinking" in body,
            msg=body,
        )

    def test_no_response_asks_what_to_fix(self) -> None:
        self.__class__.client.post(
            "/chat",
            json={
                "session_id": "phase2-no",
                "message": (
                    "basketball camp Saturday at 9 at aquatic center "
                    "https://example.com/bcamp info 928-555-0100"
                ),
            },
        )
        response = self.__class__.client.post(
            "/chat",
            json={"session_id": "phase2-no", "message": "no"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("what should we change", response.json()["response"].lower())
        self.assertFalse(get_session("phase2-no")["awaiting_confirmation"])


class ExtractDateRangeTests(unittest.TestCase):
    def test_extract_date_range_this_week(self) -> None:
        dr = extract_date_range("what's on this week")
        self.assertIsNotNone(dr)
        assert dr is not None
        today = date.today()
        self.assertEqual(dr["start"], today)
        offset = (dr["end"] - today).days
        self.assertGreaterEqual(offset, 0)
        self.assertLessEqual(offset, 6)
        self.assertEqual(dr["end"].weekday(), 6)  # Sunday

    def test_extract_date_range_next_week(self) -> None:
        dr = extract_date_range("anything going on next week")
        self.assertIsNotNone(dr)
        assert dr is not None
        today = date.today()
        self.assertEqual(dr["start"].weekday(), 0)  # Monday
        self.assertGreater(dr["start"], today)
        self.assertLessEqual((dr["start"] - today).days, 7)
        self.assertEqual((dr["end"] - dr["start"]).days, 6)

    def test_extract_date_range_this_month(self) -> None:
        dr = extract_date_range("what's happening this month")
        self.assertIsNotNone(dr)
        assert dr is not None
        today = date.today()
        self.assertEqual(dr["start"], today)
        last_day = monthrange(today.year, today.month)[1]
        self.assertEqual(dr["end"], date(today.year, today.month, last_day))

    def test_extract_date_range_next_month(self) -> None:
        dr = extract_date_range("events next month")
        self.assertIsNotNone(dr)
        assert dr is not None
        today = date.today()
        next_month = today.month + 1 if today.month < 12 else 1
        next_year = today.year if today.month < 12 else today.year + 1
        last_day = monthrange(next_year, next_month)[1]
        self.assertEqual(dr["start"], date(next_year, next_month, 1))
        self.assertEqual(dr["end"], date(next_year, next_month, last_day))


if __name__ == "__main__":
    unittest.main()
