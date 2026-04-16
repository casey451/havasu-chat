from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.intent import detect_intent, is_cancel_or_restart
from app.core.session import (
    blocking_session_expired,
    clear_session_state,
    get_session,
)
from app.db.database import SessionLocal
from app.db.models import ChatLog, Event
from app.main import app


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
