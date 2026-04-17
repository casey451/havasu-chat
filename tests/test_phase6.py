from __future__ import annotations

import os
import unittest
from datetime import date, datetime, time, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.event_quality import FIELD_PROMPTS, REVIEW_OFFER_MESSAGE, SUBMITTED_REVIEW_MESSAGE
from app.core.session import clear_session_state
from app.db.database import SessionLocal
from app.db.models import Event
from app.main import app, run_expired_review_cleanup
from app.schemas.event import EventCreate


def _login_admin(client: TestClient) -> None:
    r = client.post(
        "/admin/login",
        data={"password": "changeme"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def _make_valid_create() -> EventCreate:
    return EventCreate(
        title="Community Fair Day",
        date=date(2026, 5, 1),
        start_time=time(10, 0, 0),
        location_name="City Park",
        description="A full day of family activities and local vendors.",
        event_url="https://example.com/community-fair",
        contact_name=None,
        contact_phone=None,
    )


class Phase6Tests(unittest.TestCase):
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
            db.commit()
        clear_session_state("phase6-validation")
        clear_session_state("phase6-review-flow")
        clear_session_state("phase6-admin")

    def test_post_events_returns_friendly_message_for_invalid_title(self) -> None:
        r = self.__class__.client.post(
            "/events",
            json={
                "title": "ab",
                "date": "2026-04-20",
                "start_time": "09:00:00",
                "location_name": "Aquatic Center",
                "description": "This description is long enough to pass validation.",
                "event_url": "https://example.com/valid",
            },
        )
        self.assertEqual(r.status_code, 422)
        body = r.json()
        self.assertIn("message", body)
        self.assertIn("3 characters", body["message"])

    def test_expired_pending_review_marked_deleted(self) -> None:
        past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        payload = _make_valid_create()
        payload = payload.model_copy(update={"status": "pending_review", "admin_review_by": past})
        with SessionLocal() as db:
            ev = Event.from_create(payload)
            db.add(ev)
            db.commit()
            eid = ev.id

        n = run_expired_review_cleanup()
        self.assertGreaterEqual(n, 1)

        with SessionLocal() as db:
            row = db.get(Event, eid)
            assert row is not None
            self.assertEqual(row.status, "deleted")

    def test_admin_approve_sets_live(self) -> None:
        payload = _make_valid_create()
        payload = payload.model_copy(
            update={
                "status": "pending_review",
                "admin_review_by": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=48),
            }
        )
        with SessionLocal() as db:
            ev = Event.from_create(payload)
            db.add(ev)
            db.commit()
            eid = ev.id

        c = self.__class__.client
        _login_admin(c)
        r = c.post(f"/admin/review/{eid}", json={"action": "approve"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "live")

        with SessionLocal() as db:
            self.assertEqual(db.get(Event, eid).status, "live")

    def test_admin_reject_sets_deleted(self) -> None:
        payload = _make_valid_create()
        payload = payload.model_copy(
            update={
                "status": "pending_review",
                "admin_review_by": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=48),
            }
        )
        with SessionLocal() as db:
            ev = Event.from_create(payload)
            db.add(ev)
            db.commit()
            eid = ev.id

        c = self.__class__.client
        _login_admin(c)
        r = c.post(f"/admin/review/{eid}", json={"action": "reject"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "deleted")

    def test_chat_review_offer_after_two_bad_replies(self) -> None:
        c = self.__class__.client
        first = c.post(
            "/chat",
            json={"session_id": "phase6-review-flow", "message": "add Big Sat 9 Zoo"},
        )
        self.assertEqual(first.status_code, 200)
        self.assertIn(FIELD_PROMPTS["description"], first.json()["response"])

        second = c.post(
            "/chat",
            json={"session_id": "phase6-review-flow", "message": "short"},
        )
        self.assertEqual(second.status_code, 200)
        self.assertIn("hmm, that didn't quite work", second.json()["response"].lower())

        third = c.post(
            "/chat",
            json={"session_id": "phase6-review-flow", "message": "tiny"},
        )
        self.assertEqual(third.status_code, 200)
        self.assertEqual(third.json()["response"], REVIEW_OFFER_MESSAGE)

        fourth = c.post(
            "/chat",
            json={"session_id": "phase6-review-flow", "message": "yes"},
        )
        self.assertEqual(fourth.status_code, 200)
        self.assertEqual(fourth.json()["response"], SUBMITTED_REVIEW_MESSAGE)
        self.assertEqual(fourth.json()["data"].get("status"), "pending_review")

        with SessionLocal() as db:
            ev = db.query(Event).filter(Event.status == "pending_review").one()
            self.assertIsNotNone(ev.admin_review_by)

    def test_admin_debug_pw_reports_stripped_length(self) -> None:
        os.environ["ADMIN_PASSWORD"] = "  xy\n"
        r = self.__class__.client.get("/admin/debug-pw")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"pw_set": True, "pw_length": 2})

    def test_admin_reseed_requires_auth(self) -> None:
        c = self.__class__.client
        c.cookies.clear()
        r = c.post("/admin/reseed")
        self.assertEqual(r.status_code, 401)

    def test_admin_reseed_deletes_only_seed_rows_and_reinserts(self) -> None:
        user_ev = Event.from_create(_make_valid_create())
        user_ev.created_by = "user"
        with SessionLocal() as db:
            db.add(user_ev)
            db.commit()
            user_id = user_ev.id

        c = self.__class__.client
        _login_admin(c)
        r = c.post("/admin/reseed")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["deleted"], 0)
        self.assertEqual(body["inserted"], 27)
        self.assertEqual(body["skipped"], 0)

        with SessionLocal() as db:
            self.assertIsNotNone(db.get(Event, user_id))
            n_seed = db.query(Event).filter(Event.created_by == "seed").count()
            self.assertEqual(n_seed, 27)

        r2 = c.post("/admin/reseed")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["deleted"], 27)
        self.assertEqual(r2.json()["inserted"], 27)
        self.assertEqual(r2.json()["skipped"], 0)

        with SessionLocal() as db:
            self.assertIsNotNone(db.get(Event, user_id))
            self.assertEqual(db.query(Event).filter(Event.created_by == "seed").count(), 27)


if __name__ == "__main__":
    unittest.main()
