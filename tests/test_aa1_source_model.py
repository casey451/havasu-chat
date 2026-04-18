"""Two-tier source model (Session AA-1) — source + verified on events and programs."""

from __future__ import annotations

import os
import unittest
from datetime import date, time as time_type

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import Event, Program
from app.main import app
from app.schemas.event import EventCreate


def _sample_event(source: str = "admin", verified: bool | None = None) -> Event:
    payload = EventCreate(
        title="Two-Tier Source Test Event",
        date=date(2026, 7, 1),
        start_time=time_type(19, 0, 0),
        end_time=None,
        location_name="Rotary Park",
        description="Sample event used to verify source/verified default behavior.",
        event_url="https://example.com/aa1-event",
        contact_name=None,
        contact_phone=None,
        tags=[],
        embedding=None,
        status="live",
        created_by="user",
        admin_review_by=None,
    )
    event = Event.from_create(payload)
    if source != "admin":
        event.source = source
        event.verified = source == "admin"
    if verified is not None:
        event.verified = verified
    return event


def _sample_program(**overrides) -> Program:
    defaults = {
        "title": "Source Field Program",
        "description": "Minimal program used to exercise the source/verified fields.",
        "activity_category": "golf",
        "schedule_days": ["saturday"],
        "schedule_start_time": "09:00",
        "schedule_end_time": "10:30",
        "location_name": "Havasu Golf Academy",
        "provider_name": "Havasu Golf Academy",
        "is_active": True,
        "source": "admin",
        "verified": False,
        "tags": [],
    }
    defaults.update(overrides)
    return Program(**defaults)


class AA1SourceModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    def setUp(self) -> None:
        os.environ["ADMIN_PASSWORD"] = "changeme"
        with SessionLocal() as db:
            db.query(Event).delete()
            db.query(Program).delete()
            db.commit()

    def test_event_source_defaults_to_admin(self) -> None:
        """Event.from_create with no explicit source should default to 'admin' and auto-verify."""
        event = _sample_event()
        with SessionLocal() as db:
            db.add(event)
            db.commit()
            db.refresh(event)
        self.assertEqual(event.source, "admin")
        self.assertTrue(event.verified)

    def test_program_source_field_exists(self) -> None:
        """Program has source + verified fields and admin-sourced entries may be verified."""
        p = _sample_program(source="admin", verified=True)
        with SessionLocal() as db:
            db.add(p)
            db.commit()
            db.refresh(p)
        # Field access — the migration must have added the columns.
        self.assertEqual(p.source, "admin")
        self.assertTrue(p.verified)

        # A provider-submitted program should store source="provider" with verified defaulting False.
        p2 = _sample_program(
            title="Provider-submitted Program",
            source="provider",
            verified=False,
        )
        with SessionLocal() as db:
            db.add(p2)
            db.commit()
            db.refresh(p2)
        self.assertEqual(p2.source, "provider")
        self.assertFalse(p2.verified)

    def _login(self) -> None:
        r = self.__class__.client.post(
            "/admin/login",
            data={"password": "changeme"},
            follow_redirects=False,
        )
        self.assertEqual(r.status_code, 303)

    def test_admin_badge_renders_for_each_source(self) -> None:
        """Admin programs tab shows the correct verification badge per (source, verified) pair."""
        with SessionLocal() as db:
            db.add(_sample_program(title="Admin Row", source="admin", verified=True))
            db.add(
                _sample_program(
                    title="Provider Verified Row", source="provider", verified=True
                )
            )
            db.add(
                _sample_program(
                    title="Provider Unclaimed Row",
                    source="provider",
                    verified=False,
                )
            )
            db.add(
                _sample_program(title="Parent Row", source="parent", verified=False)
            )
            db.add(
                _sample_program(title="Scraped Row", source="scraped", verified=False)
            )
            db.commit()

        self._login()
        r = self.__class__.client.get("/admin?tab=programs")
        self.assertEqual(r.status_code, 200)
        body = r.text

        # Admin-sourced → green Verified pill
        self.assertIn("Admin Row", body)
        self.assertIn('class="pill pill-ok">Verified<', body)

        # Provider+verified → green Verified provider pill
        self.assertIn("Provider Verified Row", body)
        self.assertIn('class="pill pill-ok">Verified provider<', body)

        # Provider+unverified → yellow Provider (unclaimed) pill
        self.assertIn("Provider Unclaimed Row", body)
        self.assertIn('class="pill pill-warn">Provider (unclaimed)<', body)

        # Parent → blue Parent pill
        self.assertIn("Parent Row", body)
        self.assertIn('class="pill pill-info">Parent<', body)

        # Scraped → gray Scraped pill
        self.assertIn("Scraped Row", body)
        self.assertIn('class="pill pill-muted">Scraped<', body)


if __name__ == "__main__":
    unittest.main()
