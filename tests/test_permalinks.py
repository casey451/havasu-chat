from __future__ import annotations

import unittest
from datetime import date, time

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import Event
from app.main import app
from app.schemas.event import EventCreate


class PermalinkRouteTests(unittest.TestCase):
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

    def _create_event(self, *, title: str, status: str = "live") -> str:
        payload = EventCreate(
            title=title,
            date=date(2026, 6, 18),
            end_date=None,
            start_time=time(18, 30, 0),
            end_time=None,
            location_name="London Bridge Beach",
            description="A waterfront community event with live music and local vendors.",
            event_url="https://example.com/event",
            contact_name="Havasu Events Team",
            contact_phone="928-555-0102",
            tags=["music", "community"],
            embedding=None,
            status=status,
            created_by="user",
            admin_review_by=None,
        )
        with SessionLocal() as db:
            event = Event.from_create(payload)
            db.add(event)
            db.commit()
            db.refresh(event)
            return event.id

    def test_event_permalink_returns_html(self) -> None:
        event_id = self._create_event(title="Sunset Music Night")

        response = self.__class__.client.get(f"/events/{event_id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        self.assertIn("Sunset Music Night", response.text)

    def test_event_permalink_404_for_missing(self) -> None:
        response = self.__class__.client.get("/events/nonexistent-id")

        self.assertEqual(response.status_code, 404)
        self.assertIn("Event not found", response.text)

    def test_event_permalink_404_for_pending(self) -> None:
        event_id = self._create_event(title="Pending Draft Event", status="pending_review")

        response = self.__class__.client.get(f"/events/{event_id}")

        self.assertEqual(response.status_code, 404)
        self.assertIn("Event not found", response.text)


if __name__ == "__main__":
    unittest.main()
