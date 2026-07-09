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

    def _create_event(
        self, *, title: str, status: str = "live", location_name: str = "London Bridge Beach"
    ) -> str:
        payload = EventCreate(
            title=title,
            date=date(2026, 6, 18),
            end_date=None,
            start_time=time(18, 30, 0),
            end_time=None,
            location_name=location_name,
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

    def test_event_permalink_hides_backend_tags_section(self) -> None:
        # §3.1: the backend bucket/section "Tags" block is no longer rendered on
        # the detail page (mirrors Session 1 row-tag hiding). The event carries
        # tags=["music","community"], which previously rendered a "Tags" section.
        event_id = self._create_event(title="Tagged Community Night")
        response = self.__class__.client.get(f"/events/{event_id}")
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertNotIn("<h2>Tags</h2>", body)
        self.assertNotIn('class="tag-wrap"', body)
        # ...but the page itself still renders.
        self.assertIn("Tagged Community Night", body)

    def test_directions_link_present_for_real_venue(self) -> None:
        event_id = self._create_event(
            title="Beach Concert", location_name="London Bridge Beach"
        )
        response = self.__class__.client.get(f"/events/{event_id}")
        self.assertIn("maps/dir/?api=1", response.text)
        self.assertIn(">Directions</a>", response.text)

    def test_directions_link_suppressed_for_org_location(self) -> None:
        # F7: the parks-rec org is not a venue -> no misdirecting Directions link.
        event_id = self._create_event(
            title="Free Summer Craft Series",
            location_name="Lake Havasu City Parks & Recreation",
        )
        response = self.__class__.client.get(f"/events/{event_id}")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("maps/dir/?api=1", response.text)
        # The location text still renders.
        self.assertIn("Lake Havasu City Parks &amp; Recreation", response.text)

    def test_event_permalink_renders_image_when_present(self) -> None:
        # ED-3: an event with an image_url renders an <img> + og:image.
        event_id = self._create_event(title="Lantern Festival")
        img = "https://www.golakehavasu.com/imager/lantern.jpg"
        with SessionLocal() as db:
            ev = db.get(Event, event_id)
            ev.image_url = img
            db.commit()

        response = self.__class__.client.get(f"/events/{event_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'src="{img}"', response.text)
        self.assertIn(f'property="og:image" content="{img}"', response.text)

    def test_event_permalink_no_image_tag_when_absent(self) -> None:
        event_id = self._create_event(title="No Photo Meetup")
        response = self.__class__.client.get(f"/events/{event_id}")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("ll-event-image", response.text)

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
