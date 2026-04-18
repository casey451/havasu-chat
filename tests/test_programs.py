from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import Program
from app.main import app
from app.schemas.program import ProgramCreate


def _minimal_program_payload(**overrides: object) -> dict:
    base = {
        "title": "Junior Golf Fundamentals",
        "description": "Weekly small-group golf instruction for beginners.",
        "activity_category": "golf",
        "schedule_start_time": "09:00",
        "schedule_end_time": "10:30",
        "location_name": "Havasu Golf Academy",
        "provider_name": "Havasu Golf Academy",
    }
    base.update(overrides)
    return base


def _full_program_payload(**overrides: object) -> dict:
    base = {
        "title": "Havasu Swim Team",
        "description": "Competitive swim program with weekly practices and monthly meets.",
        "activity_category": "swim",
        "age_min": 7,
        "age_max": 14,
        "schedule_days": ["monday", "wednesday", "friday"],
        "schedule_start_time": "16:30",
        "schedule_end_time": "18:00",
        "location_name": "Havasu Aquatic Center",
        "location_address": "100 Park Ave, Lake Havasu City, AZ",
        "cost": "$85/month",
        "provider_name": "Havasu Swim Club",
        "contact_phone": "928-555-0101",
        "contact_email": "coach@havasuswim.example",
        "contact_url": "https://havasuswim.example",
        "source": "provider",
        "is_active": True,
        "tags": ["kids", "competitive"],
        "embedding": None,
    }
    base.update(overrides)
    return base


def _insert_program_directly(**overrides: object) -> Program:
    """Insert a Program via ORM to bypass the /programs rate limit in fixtures."""
    payload = ProgramCreate(**_minimal_program_payload(**overrides))
    program = Program(
        title=payload.title,
        description=payload.description,
        activity_category=payload.activity_category,
        age_min=payload.age_min,
        age_max=payload.age_max,
        schedule_days=list(payload.schedule_days),
        schedule_start_time=payload.schedule_start_time,
        schedule_end_time=payload.schedule_end_time,
        location_name=payload.location_name,
        location_address=payload.location_address,
        cost=payload.cost,
        provider_name=payload.provider_name,
        contact_phone=payload.contact_phone,
        contact_email=payload.contact_email,
        contact_url=payload.contact_url,
        source=payload.source,
        is_active=payload.is_active,
        tags=list(payload.tags),
        embedding=payload.embedding,
    )
    with SessionLocal() as db:
        db.add(program)
        db.commit()
        db.refresh(program)
    return program


class ProgramApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    def setUp(self) -> None:
        with SessionLocal() as db:
            db.query(Program).delete()
            db.commit()

    def test_create_program_minimal(self) -> None:
        r = self.__class__.client.post("/programs", json=_minimal_program_payload())
        self.assertEqual(r.status_code, 200, msg=r.text)
        body = r.json()
        self.assertEqual(body["title"], "Junior Golf Fundamentals")
        self.assertEqual(body["activity_category"], "golf")
        self.assertEqual(body["schedule_days"], [])
        self.assertTrue(body["is_active"])
        self.assertEqual(body["source"], "admin")
        self.assertIsNotNone(body["id"])
        self.assertIsNotNone(body["created_at"])
        self.assertIsNotNone(body["updated_at"])

    def test_create_program_full(self) -> None:
        r = self.__class__.client.post("/programs", json=_full_program_payload())
        self.assertEqual(r.status_code, 200, msg=r.text)
        body = r.json()
        self.assertEqual(body["activity_category"], "swim")
        self.assertEqual(body["age_min"], 7)
        self.assertEqual(body["age_max"], 14)
        self.assertEqual(body["schedule_days"], ["monday", "wednesday", "friday"])
        self.assertEqual(body["location_address"], "100 Park Ave, Lake Havasu City, AZ")
        self.assertEqual(body["cost"], "$85/month")
        self.assertEqual(body["contact_phone"], "928-555-0101")
        self.assertEqual(body["contact_email"], "coach@havasuswim.example")
        self.assertEqual(body["source"], "provider")
        self.assertEqual(sorted(body["tags"]), ["competitive", "kids"])

    def test_get_program_by_id(self) -> None:
        program = _insert_program_directly(title="Retrievable Program")
        r = self.__class__.client.get(f"/programs/{program.id}")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["id"], program.id)
        self.assertEqual(body["title"], "Retrievable Program")
        self.assertEqual(body["schedule_start_time"], "09:00")
        self.assertEqual(body["schedule_end_time"], "10:30")

    def test_list_programs(self) -> None:
        a = _insert_program_directly(title="Junior Golf A")
        b = _insert_program_directly(title="Junior Golf B")
        r = self.__class__.client.get("/programs")
        self.assertEqual(r.status_code, 200)
        titles = {item["title"] for item in r.json()}
        self.assertIn(a.title, titles)
        self.assertIn(b.title, titles)

    def test_program_schema_validation(self) -> None:
        payload = _minimal_program_payload()
        del payload["title"]
        r = self.__class__.client.post("/programs", json=payload)
        self.assertEqual(r.status_code, 422)


class ProgramSubmitFlowTests(unittest.TestCase):
    """Public parent-submission flow (Session AA-2)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    def setUp(self) -> None:
        with SessionLocal() as db:
            db.query(Program).delete()
            db.commit()

    def _minimal_submit_form(self, **overrides) -> dict:
        base = {
            "title": "Parent Submitted Basketball Clinic",
            "description": "Weekly community basketball clinic suggested by a local parent.",
            "activity_category": "basketball",
            "age_min": "",
            "age_max": "",
            "schedule_days": ["saturday"],
            "schedule_start_time": "10:00",
            "schedule_end_time": "11:30",
            "location_name": "Rotary Park",
            "location_address": "",
            "cost": "Free",
            "provider_name": "Volunteer parent group",
            "contact_phone": "",
            "contact_email": "",
            "contact_url": "",
        }
        base.update(overrides)
        return base

    def test_submit_program_form_renders(self) -> None:
        r = self.__class__.client.get("/programs/submit")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn("Submit a program", body)
        self.assertIn('name="title"', body)
        self.assertIn('name="schedule_days"', body)

    def test_submit_program_creates_parent_source_inactive(self) -> None:
        r = self.__class__.client.post(
            "/programs/submit", data=self._minimal_submit_form()
        )
        self.assertEqual(r.status_code, 200, msg=r.text[:300])
        self.assertIn("We got it", r.text)
        with SessionLocal() as db:
            rows = db.query(Program).filter(
                Program.title == "Parent Submitted Basketball Clinic"
            ).all()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.source, "parent")
        self.assertFalse(row.is_active)
        self.assertFalse(row.verified)

    def test_submit_program_ignores_self_declared_source(self) -> None:
        """Even if a submitter passes source=admin, the server forces source=parent."""
        data = self._minimal_submit_form(title="Attempted Self-Declared Admin")
        # Form field for source doesn't exist in the template — but if someone
        # crafts a request with one, the server should ignore it.
        data["source"] = "admin"  # type: ignore[assignment]
        data["is_active"] = "1"  # type: ignore[assignment]
        r = self.__class__.client.post("/programs/submit", data=data)
        self.assertEqual(r.status_code, 200, msg=r.text[:300])
        with SessionLocal() as db:
            row = db.query(Program).filter(
                Program.title == "Attempted Self-Declared Admin"
            ).one()
        self.assertEqual(row.source, "parent")
        self.assertFalse(row.is_active)
        self.assertFalse(row.verified)

    def test_submit_program_invalid_input_rerenders_with_error(self) -> None:
        r = self.__class__.client.post(
            "/programs/submit",
            data=self._minimal_submit_form(title="xx"),  # too short
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("Title must be at least 3 characters", r.text)
        # Form should be re-rendered with submitted values preserved.
        self.assertIn('value="xx"', r.text)

    def test_submitted_program_absent_from_public_list(self) -> None:
        """A parent submission should not appear in GET /programs until admin activates it."""
        self.__class__.client.post(
            "/programs/submit",
            data=self._minimal_submit_form(title="Hidden Until Approved"),
        )
        r = self.__class__.client.get("/programs")
        self.assertEqual(r.status_code, 200)
        titles = {item["title"] for item in r.json()}
        self.assertNotIn("Hidden Until Approved", titles)


if __name__ == "__main__":
    unittest.main()
