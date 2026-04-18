from __future__ import annotations

import os
import time
import unittest
from datetime import UTC, date, datetime, timedelta, time as time_type
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.extraction import _deterministic_embedding
from app.core.intent import detect_intent, is_cancel_or_restart
from app.core.session import (
    blocking_session_expired,
    clear_session_state,
    get_session,
)
from app.db.database import SessionLocal
from app.db.models import ChatLog, Event, Program
from app.main import app
from app.schemas.event import EventCreate


class Phase8StabilizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    def setUp(self) -> None:
        with SessionLocal() as db:
            db.query(ChatLog).delete()
            db.query(Event).delete()
            db.commit()
        clear_session_state("phase8-intent")
        clear_session_state("phase8-cancel")
        clear_session_state("phase8-stale")
        clear_session_state("phase8-health")

    def test_single_word_activity_is_search(self) -> None:
        self.assertEqual(detect_intent("golf"), "SEARCH_EVENTS")
        self.assertEqual(detect_intent("Pickleball?"), "SEARCH_EVENTS")

    def test_question_biases_to_search(self) -> None:
        self.assertEqual(detect_intent("anything fun Saturday?"), "SEARCH_EVENTS")

    def test_reset_cancels_word_boundary(self) -> None:
        self.assertTrue(is_cancel_or_restart("please reset"))
        self.assertTrue(is_cancel_or_restart("reset"))
        self.assertFalse(is_cancel_or_restart("preset calibration"))

    def test_blocking_session_expires(self) -> None:
        sid = "phase8-stale"
        s = get_session(sid)
        s["awaiting_confirmation"] = True
        start = 1_000_000.0
        s["blocking_mono"] = start
        with patch("app.core.session.time.monotonic", return_value=start + 301):
            self.assertTrue(blocking_session_expired(s))

    def test_stale_session_returns_warm_message(self) -> None:
        sid = "phase8-stale"
        s = get_session(sid)
        s["awaiting_confirmation"] = True
        s["blocking_mono"] = time.monotonic() - 400
        r = self.__class__.client.post("/chat", json={"session_id": sid, "message": "yes"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("cleared where we left off", r.json()["response"].lower())

    def test_health_reports_db_and_event_count(self) -> None:
        r = self.__class__.client.get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body.get("db_connected"))
        self.assertIsInstance(body.get("event_count"), int)

    def test_health_responds_within_2_seconds(self) -> None:
        start = time.monotonic()
        r = self.__class__.client.get("/health")
        elapsed = time.monotonic() - start
        self.assertEqual(r.status_code, 200)
        self.assertLess(elapsed, 2.0, f"/health took {elapsed:.3f}s (must be < 2s)")

    def test_chat_logs_written_for_turn(self) -> None:
        self.__class__.client.post(
            "/chat",
            json={"session_id": "phase8-intent", "message": "what events do you have"},
        )
        with SessionLocal() as db:
            n = db.query(ChatLog).filter(ChatLog.session_id == "phase8-intent").count()
        self.assertGreaterEqual(n, 2)

    def test_admin_card_shows_tags_when_present(self) -> None:
        os.environ["ADMIN_PASSWORD"] = "changeme"
        with SessionLocal() as db:
            ev = Event.from_create(
                EventCreate(
                    title="Admin Tag Visibility Gig",
                    date=date(2026, 6, 10),
                    start_time=time_type(19, 0, 0),
                    end_time=None,
                    location_name="London Bridge Resort",
                    description="Live music night for admin tag test.",
                    event_url="https://example.com/admin-tags",
                    contact_name=None,
                    contact_phone=None,
                    tags=["admin-tag-jazz", "outdoor"],
                    embedding=None,
                    status="live",
                    created_by="user",
                    admin_review_by=None,
                )
            )
            db.add(ev)
            db.commit()

        c = self.__class__.client
        r_login = c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
        self.assertEqual(r_login.status_code, 303)
        r = c.get("/admin?tab=live&sort=newest")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn("admin-tag-jazz", body)
        self.assertIn("tag-wrap", body)
        self.assertIn('class="tag"', body)

    def test_admin_card_shows_fallback_badge_when_no_real_embedding(self) -> None:
        os.environ["ADMIN_PASSWORD"] = "changeme"
        fb = _deterministic_embedding("unique admin fallback probe xyz")
        self.assertEqual(len(fb), 32)
        with SessionLocal() as db:
            ev = Event.from_create(
                EventCreate(
                    title="Fallback Embedding Row",
                    date=date(2026, 6, 11),
                    start_time=time_type(18, 0, 0),
                    end_time=None,
                    location_name="Aquatic Center",
                    description="Seeded for deterministic embedding badge.",
                    event_url="https://example.com/fallback-emb",
                    contact_name=None,
                    contact_phone=None,
                    tags=[],
                    embedding=fb,
                    status="live",
                    created_by="user",
                    admin_review_by=None,
                )
            )
            db.add(ev)
            db.commit()

        c = self.__class__.client
        r_login = c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
        self.assertEqual(r_login.status_code, 303)
        r = c.get("/admin?tab=live&sort=newest")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Fallback embedding", r.text)

    def test_analytics_requires_admin_auth(self) -> None:
        self.__class__.client.cookies.clear()
        r = self.__class__.client.get("/admin/analytics", follow_redirects=False)
        self.assertIn(r.status_code, (302, 303))
        self.assertIn("login", (r.headers.get("location") or "").lower())

    def test_analytics_renders_with_empty_data(self) -> None:
        os.environ["ADMIN_PASSWORD"] = "changeme"
        c = self.__class__.client
        self.assertEqual(c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False).status_code, 303)
        r = c.get("/admin/analytics")
        self.assertEqual(r.status_code, 200)
        self.assertIn("No data yet", r.text)
        self.assertIn("Analytics", r.text)

    def test_analytics_renders_with_seeded_data(self) -> None:
        os.environ["ADMIN_PASSWORD"] = "changeme"
        now = datetime.now(UTC)
        sid = "phase8-analytics-seed"
        user_msg = "unique analytics query xyz"
        assistant_msg = (
            "No zydeco in the system yet. If you hear of one, add it here and help others find it — just tell me the details 👋"
        )
        with SessionLocal() as db:
            db.add(
                ChatLog(
                    session_id=sid,
                    message=user_msg,
                    role="user",
                    intent=None,
                    created_at=now,
                )
            )
            db.add(
                ChatLog(
                    session_id=sid,
                    message=assistant_msg,
                    role="assistant",
                    intent="SEARCH_EVENTS",
                    created_at=now + timedelta(seconds=2),
                )
            )
            db.add(
                Event.from_create(
                    EventCreate(
                        title="Analytics Funnel Event",
                        date=date(2026, 7, 1),
                        start_time=time_type(12, 0, 0),
                        end_time=None,
                        location_name="Test Venue Row",
                        description="Seeded only for admin analytics funnel row in the last thirty days.",
                        event_url="https://example.com/analytics-funnel",
                        contact_name=None,
                        contact_phone=None,
                        tags=[],
                        embedding=None,
                        status="live",
                        created_by="user",
                        admin_review_by=None,
                    )
                )
            )
            db.commit()

        c = self.__class__.client
        self.assertEqual(c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False).status_code, 303)
        r = c.get("/admin/analytics")
        self.assertEqual(r.status_code, 200)
        self.assertIn(user_msg.lower(), r.text.lower())
        self.assertIn("unique analytics query xyz", r.text)
        self.assertRegex(r.text, r"Live \(approved\)</td>\s*<td>1</td>")


class AdminProgramsTests(unittest.TestCase):
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
            db.query(Program).delete()
            db.commit()

    def _login(self) -> None:
        r = self.__class__.client.post(
            "/admin/login",
            data={"password": "changeme"},
            follow_redirects=False,
        )
        self.assertEqual(r.status_code, 303)

    def _insert_program(self, **overrides) -> Program:
        defaults = {
            "title": "Admin UI Golf Lessons",
            "description": "Weekly small-group golf instruction for admin UI coverage.",
            "activity_category": "golf",
            "age_min": 6,
            "age_max": 12,
            "schedule_days": ["saturday"],
            "schedule_start_time": "09:00",
            "schedule_end_time": "10:30",
            "location_name": "Havasu Golf Academy",
            "provider_name": "Havasu Golf Academy",
            "is_active": True,
            "source": "admin",
            "tags": ["kids"],
        }
        defaults.update(overrides)
        program = Program(**defaults)
        with SessionLocal() as db:
            db.add(program)
            db.commit()
            db.refresh(program)
        return program

    def test_admin_programs_tab_shows_programs(self) -> None:
        p = self._insert_program(title="Visibility Check Program")
        self._login()
        r = self.__class__.client.get("/admin?tab=programs")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Visibility Check Program", r.text)
        self.assertIn("Every Saturday", r.text)
        self.assertIn("Active", r.text)
        self.assertIn(f"/admin/programs/{p.id}/edit", r.text)

    def test_admin_create_program(self) -> None:
        self._login()
        r = self.__class__.client.post(
            "/admin/programs",
            data={
                "title": "Created Via Admin Form",
                "description": "Program created through the admin UI during the Z-3 test run.",
                "activity_category": "swim",
                "age_min": "5",
                "age_max": "10",
                "schedule_days": ["monday", "wednesday"],
                "schedule_start_time": "16:00",
                "schedule_end_time": "17:00",
                "location_name": "Havasu Aquatic Center",
                "location_address": "",
                "cost": "Free",
                "provider_name": "City Parks & Rec",
                "contact_phone": "",
                "contact_email": "",
                "contact_url": "",
                "source": "admin",
                "is_active": "1",
                "tags": "swim, kids",
            },
            follow_redirects=False,
        )
        self.assertEqual(r.status_code, 303, msg=r.text[:300])
        with SessionLocal() as db:
            rows = db.query(Program).filter(Program.title == "Created Via Admin Form").all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].schedule_days, ["monday", "wednesday"])
        self.assertEqual(rows[0].cost, "Free")
        self.assertEqual(sorted(rows[0].tags), ["kids", "swim"])
        self.assertTrue(rows[0].is_active)

    def test_admin_edit_program(self) -> None:
        p = self._insert_program(title="Edit Me Golf", cost="$20")
        self._login()
        r = self.__class__.client.post(
            f"/admin/programs/{p.id}/update",
            data={
                "title": "Edited Golf Program",
                "description": p.description,
                "activity_category": p.activity_category,
                "age_min": str(p.age_min or ""),
                "age_max": str(p.age_max or ""),
                "schedule_days": list(p.schedule_days or []),
                "schedule_start_time": p.schedule_start_time,
                "schedule_end_time": p.schedule_end_time,
                "location_name": p.location_name,
                "location_address": p.location_address or "",
                "cost": "$25/class",
                "provider_name": p.provider_name,
                "contact_phone": p.contact_phone or "",
                "contact_email": p.contact_email or "",
                "contact_url": p.contact_url or "",
                "source": p.source,
                "is_active": "1",
                "tags": ", ".join(p.tags or []),
            },
            follow_redirects=False,
        )
        self.assertEqual(r.status_code, 303, msg=r.text[:300])
        with SessionLocal() as db:
            refreshed = db.get(Program, p.id)
        assert refreshed is not None
        self.assertEqual(refreshed.title, "Edited Golf Program")
        self.assertEqual(refreshed.cost, "$25/class")

    def test_admin_deactivate_program(self) -> None:
        p = self._insert_program(title="Soon Deactivated")
        self._login()
        r = self.__class__.client.post(
            f"/admin/programs/{p.id}/deactivate",
            follow_redirects=False,
        )
        self.assertEqual(r.status_code, 303)
        with SessionLocal() as db:
            refreshed = db.get(Program, p.id)
        assert refreshed is not None
        self.assertFalse(refreshed.is_active)

        # Deactivated programs should not appear in /programs list endpoint.
        list_r = self.__class__.client.get("/programs")
        self.assertEqual(list_r.status_code, 200)
        titles = {item["title"] for item in list_r.json()}
        self.assertNotIn("Soon Deactivated", titles)


class AdminModerationQueueTests(unittest.TestCase):
    """Unified moderation queue (Session AB)."""

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

    def _login(self) -> None:
        r = self.__class__.client.post(
            "/admin/login",
            data={"password": "changeme"},
            follow_redirects=False,
        )
        self.assertEqual(r.status_code, 303)

    def _insert_pending_event(self, title: str, **overrides) -> Event:
        base = {
            "title": title,
            "date": date(2026, 8, 1),
            "start_time": time_type(18, 0, 0),
            "end_time": None,
            "location_name": "Rotary Park",
            "description": "A community event happening in Lake Havasu for all ages to enjoy.",
            "event_url": "https://example.com/event",
            "contact_name": None,
            "contact_phone": None,
            "tags": [],
            "embedding": None,
            "status": "pending_review",
            "created_by": "user",
            "admin_review_by": None,
        }
        base.update(overrides)
        ev = Event.from_create(EventCreate(**base))
        ev.status = "pending_review"
        with SessionLocal() as db:
            db.add(ev)
            db.commit()
            db.refresh(ev)
        return ev

    def _insert_parent_program(self, title: str, **overrides) -> Program:
        defaults = {
            "title": title,
            "description": "Weekly class submitted by a parent, pending admin approval.",
            "activity_category": "swim",
            "schedule_days": ["saturday"],
            "schedule_start_time": "09:00",
            "schedule_end_time": "10:00",
            "location_name": "Havasu Aquatic Center",
            "provider_name": "Local parent",
            "source": "parent",
            "is_active": False,
            "verified": False,
            "tags": [],
        }
        defaults.update(overrides)
        p = Program(**defaults)
        with SessionLocal() as db:
            db.add(p)
            db.commit()
            db.refresh(p)
        return p

    def test_queue_renders_pending_events_and_parent_programs(self) -> None:
        self._insert_pending_event("Queue Visible Event")
        self._insert_parent_program("Queue Visible Program")
        # A non-parent inactive program should NOT appear in the queue.
        self._insert_parent_program(
            "Admin Inactive Program",
            source="admin",
        )

        self._login()
        r = self.__class__.client.get("/admin?tab=queue")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn("Queue Visible Event", body)
        self.assertIn("Queue Visible Program", body)
        self.assertNotIn("Admin Inactive Program", body)
        self.assertIn("Moderation queue", body)

    def test_queue_flags_duplicates_and_all_caps_and_short_desc(self) -> None:
        # Seed a live event that shares a title with a pending submission.
        live = EventCreate(
            title="Concert Night",
            date=date(2026, 8, 2),
            start_time=time_type(19, 0, 0),
            end_time=None,
            location_name="Some Venue",
            description="A live concert night at a permanent venue in town.",
            event_url="https://example.com/live",
            contact_name=None,
            contact_phone=None,
            tags=[],
            embedding=None,
            status="live",
            created_by="user",
            admin_review_by=None,
        )
        with SessionLocal() as db:
            db.add(Event.from_create(live))
            db.commit()

        # Pending with same title, all-caps, short desc, and suspicious URL.
        # Built via the ORM directly because EventCreate enforces a 20-char
        # description minimum — the queue's "Short description" flag exists
        # precisely to catch rows that slip past (or predate) that rule.
        with SessionLocal() as db:
            pending = Event(
                title="CONCERT NIGHT",
                normalized_title="concert night",
                date=date(2026, 8, 10),
                start_time=time_type(19, 0, 0),
                end_time=None,
                location_name="Some Venue",
                location_normalized="some venue",
                description="Too short.",
                event_url="https://bit.ly/mystery",
                contact_name=None,
                contact_phone=None,
                tags=[],
                embedding=None,
                status="pending_review",
                source="admin",
                verified=False,
                created_by="user",
            )
            db.add(pending)
            db.commit()

        self._login()
        r = self.__class__.client.get("/admin?tab=queue")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn("Duplicate title", body)
        self.assertIn("All caps", body)
        self.assertIn("Suspicious URL", body)
        self.assertIn("Short description", body)

    def test_queue_approve_event_flow(self) -> None:
        ev = self._insert_pending_event("Approvable Event")
        self._login()
        r = self.__class__.client.post(
            f"/admin/event/{ev.id}/approve",
            follow_redirects=False,
        )
        self.assertEqual(r.status_code, 303)
        with SessionLocal() as db:
            refreshed = db.get(Event, ev.id)
        assert refreshed is not None
        self.assertEqual(refreshed.status, "live")

    def test_queue_approve_parent_program_flow(self) -> None:
        p = self._insert_parent_program("Approvable Parent Program")
        self._login()
        r = self.__class__.client.post(
            f"/admin/programs/{p.id}/activate",
            follow_redirects=False,
        )
        self.assertEqual(r.status_code, 303)
        with SessionLocal() as db:
            refreshed = db.get(Program, p.id)
        assert refreshed is not None
        self.assertTrue(refreshed.is_active)

    def test_queue_empty_state(self) -> None:
        self._login()
        r = self.__class__.client.get("/admin?tab=queue")
        self.assertEqual(r.status_code, 200)
        self.assertIn("You're caught up", r.text)

    def test_programs_reseed_requires_auth(self) -> None:
        """Unauthenticated reseed call must not run the import."""
        # Prior tests may have set an admin cookie on the shared TestClient;
        # clear it so this call is genuinely unauthenticated.
        self.__class__.client.cookies.clear()
        r = self.__class__.client.post(
            "/admin/programs-reseed?dry_run=true", follow_redirects=False
        )
        # _guard returns a redirect for unauthenticated; the endpoint converts
        # that into a 401.
        self.assertIn(r.status_code, (401, 302, 303))

    def test_programs_reseed_dry_run_returns_stats(self) -> None:
        """Authenticated dry run returns the expected stats keys without writing."""
        with SessionLocal() as db:
            before = db.query(Program).count()
        self._login()
        r = self.__class__.client.post("/admin/programs-reseed?dry_run=true")
        self.assertEqual(r.status_code, 200, msg=r.text[:300])
        body = r.json()
        for key in (
            "programs_built",
            "events_built",
            "programs_inserted",
            "programs_skipped_idempotent",
            "events_inserted",
            "events_skipped_idempotent",
            "dry_run",
            "source_file",
        ):
            self.assertIn(key, body)
        self.assertTrue(body["dry_run"])
        # Dry run must not insert anything.
        with SessionLocal() as db:
            after = db.query(Program).count()
        self.assertEqual(before, after)
