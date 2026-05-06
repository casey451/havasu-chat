"""Slice 53 (Backlog #30) — `Program.@validates` dual-write to typed time columns.

Three wiring tests covering the `@validates("schedule_start_time", "schedule_end_time")`
decorator on `Program`:

1. Constructor kwargs populate the typed columns in-memory (catches the
   `__init__`-fires-validator path).
2. Attribute assignment populates the typed columns in-memory (catches the
   `__setattr__`-fires-validator path used by the admin update handler).
3. Round-trip through `db.add` + `db.commit` + fresh-session reload confirms
   the typed columns actually persist to disk — a `@validates` that fires in
   `__init__` but somehow fails to flush would pass tests 1 and 2 silently.
"""

from __future__ import annotations

import unittest
from datetime import time as time_type

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import Event, Program
from app.main import app


def _sample_program(**overrides) -> Program:
    defaults = {
        "title": "Typed Time Test Program",
        "description": "Exercises @validates dual-write to schedule_*_time_typed.",
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


class ProgramTypedTimeDualWriteTests(unittest.TestCase):
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
            db.query(Program).delete()
            db.commit()

    def test_constructor_populates_typed_columns_in_memory(self) -> None:
        """Program(schedule_start_time=...) fires @validates and sets the typed columns."""
        p = _sample_program(schedule_start_time="09:00", schedule_end_time="10:30")
        self.assertEqual(p.schedule_start_time, "09:00")
        self.assertEqual(p.schedule_end_time, "10:30")
        self.assertEqual(p.schedule_start_time_typed, time_type(9, 0))
        self.assertEqual(p.schedule_end_time_typed, time_type(10, 30))

    def test_attribute_assignment_populates_typed_column_in_memory(self) -> None:
        """program.schedule_*_time = "..." fires @validates and updates the typed column.

        This is the writer path used by app/admin/router.py:1642-1649 (admin program
        update handler). If @validates only fired on __init__, this test would still
        pass test_constructor_* but break this one.
        """
        p = _sample_program(schedule_start_time="09:00", schedule_end_time="10:30")
        # Reassign both fields after construction — mirrors the admin update path.
        p.schedule_start_time = "14:30"
        p.schedule_end_time = "16:00"
        self.assertEqual(p.schedule_start_time_typed, time_type(14, 30))
        self.assertEqual(p.schedule_end_time_typed, time_type(16, 0))

    def test_typed_columns_persist_through_commit_refresh(self) -> None:
        """Round-trip: write through ORM, fresh-session reload, typed columns survive.

        Catches the silent failure mode where @validates fires in __init__ but the
        typed columns aren't actually mapped to DB columns (or aren't included in
        the INSERT). A test that only checks in-memory state would miss this.
        """
        p = _sample_program(schedule_start_time="11:15", schedule_end_time="12:45")
        with SessionLocal() as db:
            db.add(p)
            db.commit()
            program_id = p.id

        # Fresh session — load a brand-new instance from disk.
        with SessionLocal() as db:
            loaded = db.query(Program).filter(Program.id == program_id).first()
            self.assertIsNotNone(loaded)
            assert loaded is not None  # type narrowing
            # String columns intact (source of truth through Slice 55).
            self.assertEqual(loaded.schedule_start_time, "11:15")
            self.assertEqual(loaded.schedule_end_time, "12:45")
            # Typed columns persisted from the @validates dual-write.
            self.assertEqual(loaded.schedule_start_time_typed, time_type(11, 15))
            self.assertEqual(loaded.schedule_end_time_typed, time_type(12, 45))


if __name__ == "__main__":
    unittest.main()
