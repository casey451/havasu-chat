from __future__ import annotations

import unittest
from datetime import date, time

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import Event
from app.main import app
from app.schemas.event import EventCreate


class Phase1ApiTests(unittest.TestCase):
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

    def test_list_events(self) -> None:
        payload = EventCreate(
            title="Soccer Clinic",
            date=date(2026, 4, 19),
            end_date=None,
            start_time=time(10, 30, 0),
            end_time=None,
            location_name="Community Park",
            description="An outdoor clinic for beginner soccer players this Sunday.",
            event_url="https://example.com/soccer-clinic",
            contact_name=None,
            contact_phone=None,
            tags=["sports"],
            embedding=None,
            status="live",
            created_by="user",
            admin_review_by=None,
        )
        with SessionLocal() as db:
            db.add(Event.from_create(payload))
            db.commit()

        response = self.__class__.client.get("/events")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(len(body), 1)
        self.assertTrue(any(event["title"] == "Soccer Clinic" for event in body))


if __name__ == "__main__":
    unittest.main()
