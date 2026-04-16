from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.core.session import clear_session_state, get_session
from app.db.database import SessionLocal
from app.db.models import Event
from app.main import app


class Phase2ChatTests(unittest.TestCase):
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
        clear_session_state("phase2-add")
        clear_session_state("phase2-unclear")
        clear_session_state("phase2-no")

    def test_add_event_flow_end_to_end(self) -> None:
        first = self.__class__.client.post(
            "/chat",
            json={
                "session_id": "phase2-add",
                "message": (
                    "basketball camp Saturday at 9 at aquatic center "
                    "https://example.com/bcamp info 928-555-0100"
                ),
            },
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["intent"], "ADD_EVENT")
        self.assertIn("Sound right?", first.json()["response"])

        second = self.__class__.client.post(
            "/chat",
            json={"session_id": "phase2-add", "message": "yes"},
        )
        self.assertEqual(second.status_code, 200)
        self.assertIn("live", second.json()["response"].lower())

        with SessionLocal() as db:
            events = db.query(Event).all()
            self.assertTrue(any(e.title.startswith("Basketball Camp") for e in events))

    def test_gibberish_biases_to_search_then_asks_date(self) -> None:
        response = self.__class__.client.post(
            "/chat",
            json={"session_id": "phase2-unclear", "message": "quantum flux capacitor settings"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intent"], "SEARCH_EVENTS")
        body = response.json()["response"].lower()
        self.assertTrue(
            "nothing yet" in body or "tighten" in body or "when are you thinking" in body,
            msg=body,
        )

    def test_no_response_asks_what_to_fix(self) -> None:
        self.__class__.client.post(
            "/chat",
            json={
                "session_id": "phase2-no",
                "message": (
                    "basketball camp Saturday at 9 at aquatic center "
                    "https://example.com/bcamp info 928-555-0100"
                ),
            },
        )
        response = self.__class__.client.post(
            "/chat",
            json={"session_id": "phase2-no", "message": "no"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("what should we change", response.json()["response"].lower())
        self.assertFalse(get_session("phase2-no")["awaiting_confirmation"])


if __name__ == "__main__":
    unittest.main()
