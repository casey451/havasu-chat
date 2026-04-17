from __future__ import annotations

import os
import time
import unittest
from datetime import date, time as time_type
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
from app.db.models import ChatLog, Event
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
