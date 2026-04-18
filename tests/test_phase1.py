from __future__ import annotations

import unittest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import Event
from app.main import app


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

    def test_create_event(self) -> None:
        response = self.__class__.client.post(
            "/events",
            json={
                "title": "Basketball Camp",
                "date": "2026-04-18",
                "start_time": "09:00:00",
                "end_time": None,
                "location_name": "Aquatic Center",
                "description": "A weekend basketball camp for local kids and families.",
                "event_url": "https://example.com/basketball-camp",
                "contact_name": None,
                "contact_phone": None,
                "tags": ["sports", "kids"],
                "embedding": None,
                "status": "live",
                "created_by": "user",
                "admin_review_by": None,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["title"], "Basketball Camp")
        self.assertEqual(payload["normalized_title"], "basketball camp")
        self.assertEqual(payload["location_normalized"], "aquatic center")

    def test_list_events(self) -> None:
        self.__class__.client.post(
            "/events",
            json={
                "title": "Soccer Clinic",
                "date": "2026-04-19",
                "start_time": "10:30:00",
                "end_time": None,
                "location_name": "Community Park",
                "description": "An outdoor clinic for beginner soccer players this Sunday.",
                "event_url": "https://example.com/soccer-clinic",
                "contact_name": None,
                "contact_phone": None,
                "tags": ["sports"],
                "embedding": None,
                "status": "live",
                "created_by": "user",
                "admin_review_by": None,
            },
        )

        response = self.__class__.client.get("/events")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(len(payload), 1)
        self.assertTrue(any(event["title"] == "Soccer Clinic" for event in payload))


if __name__ == "__main__":
    unittest.main()
