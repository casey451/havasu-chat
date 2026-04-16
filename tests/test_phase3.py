from __future__ import annotations

import unittest
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.core.session import clear_session_state, get_session
from app.db.database import SessionLocal
from app.db.models import Event
from app.main import app
from app.schemas.event import EventCreate


class Phase3SearchTests(unittest.TestCase):
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
        clear_session_state("phase3-weekend")
        clear_session_state("phase3-empty")
        clear_session_state("phase3-date-first")

    def test_weekend_search_asks_activity_then_returns_grouped_results(self) -> None:
        saturday = _next_weekday(date.today(), 5)
        with SessionLocal() as db:
            for i in range(4):
                event = Event.from_create(
                    EventCreate(
                        title=f"Basketball Clinic {i + 1}",
                        date=saturday,
                        start_time="09:00:00",
                        end_time=None,
                        location_name="Aquatic Center",
                        description="Sports training session for kids and teens.",
                        event_url="https://example.com/basketball-clinic",
                        contact_name=None,
                        contact_phone=None,
                        tags=["sports"],
                        embedding=None,
                        status="live",
                        created_by="user",
                        admin_review_by=None,
                    )
                )
                db.add(event)
            db.commit()

        first = self.__class__.client.post(
            "/chat",
            json={"session_id": "phase3-weekend", "message": "something for my 10 year old this weekend"},
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["response"], "What kind of thing — sports, arts, something else?")
        self.assertTrue(get_session("phase3-weekend")["awaiting_search_clarification"])

        second = self.__class__.client.post(
            "/chat",
            json={"session_id": "phase3-weekend", "message": "sports"},
        )
        self.assertEqual(second.status_code, 200)
        self.assertIn("⚽ Sports", second.json()["response"])
        self.assertIn("Basketball Clinic", second.json()["response"])

    def test_empty_search_returns_required_empty_message(self) -> None:
        response = self.__class__.client.post(
            "/chat",
            json={"session_id": "phase3-empty", "message": "anything this weekend sports"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Nothing on the list", response.json()["response"])

    def test_missing_date_asks_date_first_then_activity(self) -> None:
        first = self.__class__.client.post(
            "/chat",
            json={"session_id": "phase3-date-first", "message": "anything for kids"},
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["response"], "When works for you — this weekend, or a specific day?")

        second = self.__class__.client.post(
            "/chat",
            json={"session_id": "phase3-date-first", "message": "this weekend"},
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["response"], "What kind of thing — sports, arts, something else?")


def _next_weekday(today: date, weekday: int) -> date:
    days_ahead = (weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


if __name__ == "__main__":
    unittest.main()
