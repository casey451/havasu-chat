from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.core.session import clear_session_state
from app.db.database import SessionLocal
from app.db.models import Event
from app.main import app


class Phase4DuplicateTests(unittest.TestCase):
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
        clear_session_state("phase4-original")
        clear_session_state("phase4-duplicate")
        clear_session_state("phase4-different")

    def test_submitting_same_event_twice_is_caught(self) -> None:
        self.__class__.client.post(
            "/chat",
            json={
                "session_id": "phase4-original",
                "message": (
                    "basketball camp Saturday at 9 at aquatic center "
                    "https://example.com/bcamp info 928-555-0100"
                ),
            },
        )
        first_confirm = self.__class__.client.post(
            "/chat",
            json={"session_id": "phase4-original", "message": "yes"},
        )
        self.assertEqual(first_confirm.status_code, 200)
        self.assertIn("live", first_confirm.json()["response"].lower())

        self.__class__.client.post(
            "/chat",
            json={
                "session_id": "phase4-duplicate",
                "message": (
                    "basketball camp Saturday at 9 at aquatic center "
                    "https://example.com/bcamp info 928-555-0100"
                ),
            },
        )
        duplicate_confirm = self.__class__.client.post(
            "/chat",
            json={"session_id": "phase4-duplicate", "message": "yes"},
        )
        self.assertEqual(duplicate_confirm.status_code, 200)
        dup = duplicate_confirm.json()["response"]
        self.assertIn("Heads up", dup)
        self.assertIn("Same one?", dup)
        self.assertIn("Basketball Camp", dup)

    def test_clearly_different_event_is_not_flagged(self) -> None:
        self.__class__.client.post(
            "/chat",
            json={
                "session_id": "phase4-original",
                "message": (
                    "basketball camp Saturday at 9 at aquatic center "
                    "https://example.com/bcamp info 928-555-0100"
                ),
            },
        )
        self.__class__.client.post(
            "/chat",
            json={"session_id": "phase4-original", "message": "yes"},
        )

        first = self.__class__.client.post(
            "/chat",
            json={
                "session_id": "phase4-different",
                "message": (
                    "art workshop Tuesday at 3 at library https://example.com/art info 928-555-0200"
                ),
            },
        )
        self.assertEqual(first.status_code, 200)
        self.assertIn("Sound right?", first.json()["response"])

        second = self.__class__.client.post(
            "/chat",
            json={"session_id": "phase4-different", "message": "yes"},
        )
        self.assertEqual(second.status_code, 200)
        self.assertIn("live", second.json()["response"].lower())

        with SessionLocal() as db:
            events = db.query(Event).all()
            self.assertEqual(len(events), 2)


if __name__ == "__main__":
    unittest.main()
