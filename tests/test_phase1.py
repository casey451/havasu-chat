from __future__ import annotations

import unittest
from datetime import date, time, timedelta

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

    def tearDown(self) -> None:
        # The seeded event lands in "this weekend"; without symmetric cleanup it
        # leaks into the shared session DB and trips later chat-tier tests
        # (e.g. test_phase2_integration's "this weekend" query) into a real
        # retrieval/LLM path. Clear after each test to keep the class isolated.
        with SessionLocal() as db:
            db.query(Event).delete()
            db.commit()

    def test_list_events(self) -> None:
        # Land inside the default /api/events window (today .. today+14d).
        soon = date.today() + timedelta(days=3)
        payload = EventCreate(
            title="Soccer Clinic",
            date=soon,
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

        # WP-7: /events no longer serves raw JSON (it leaked embedding/source).
        # It now 301s to the human /events-ui; the public JSON contract lives at
        # /api/events with a scrubbed serializer.
        redirect = self.__class__.client.get("/events", follow_redirects=False)
        self.assertEqual(redirect.status_code, 301)
        self.assertEqual(redirect.headers["location"], "/events-ui")

        response = self.__class__.client.get("/api/events")
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertGreaterEqual(len(items), 1)
        self.assertTrue(any(event["title"] == "Soccer Clinic" for event in items))


if __name__ == "__main__":
    unittest.main()
