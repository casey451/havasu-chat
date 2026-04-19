from __future__ import annotations

import unittest
from pathlib import Path

from sqlalchemy.orm import Session

from app.chat.entity_matcher import (
    match_entity,
    match_entity_with_rows,
    refresh_entity_matcher,
    reset_entity_matcher,
)
from app.db.database import SessionLocal
from app.db.models import Program
from app.schemas.program import ProgramCreate


def _insert_program(db: Session, provider_name: str) -> str:
    payload = ProgramCreate(
        title="Test activity for entity matcher",
        description="Twenty chars minimum here.",
        activity_category="sports",
        schedule_start_time="09:00",
        schedule_end_time="10:00",
        location_name="Lake Havasu City",
        provider_name=provider_name,
        tags=["entity_matcher_test"],
    )
    p = Program(
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
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id


class EntityMatcherRowsTests(unittest.TestCase):
    def test_sonics_alias(self) -> None:
        canon = "Universal Gymnastics and All Star Cheer — Sonics"
        m = match_entity_with_rows("sonics gymnastics cost", [canon])
        self.assertIsNotNone(m)
        self.assertEqual(m[0], canon)
        self.assertGreater(m[1], 75.0)

    def test_altitude_short_name(self) -> None:
        canon = "Altitude Trampoline Park — Lake Havasu City"
        m = match_entity_with_rows("where is altitude trampoline park", [canon])
        self.assertIsNotNone(m)
        self.assertEqual(m[0], canon)

    def test_bmx_alias(self) -> None:
        canon = "Lake Havasu City BMX"
        m = match_entity_with_rows("how much does bmx cost", [canon])
        self.assertIsNotNone(m)
        self.assertEqual(m[0], canon)

    def test_below_threshold(self) -> None:
        m = match_entity_with_rows("quantum physics tutoring seattle", ["Lake Havasu City BMX"])
        self.assertIsNone(m)

    def test_fixture_file_exists(self) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "havasu_chat_test_queries.txt"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("DATE_LOOKUP", text)
        self.assertGreater(len([ln for ln in text.splitlines() if "|" in ln and not ln.strip().startswith("#")]), 80)


class EntityMatcherDbTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_entity_matcher()
        self._ids: list[str] = []

    def tearDown(self) -> None:
        with SessionLocal() as db:
            for pid in self._ids:
                row = db.get(Program, pid)
                if row is not None:
                    db.delete(row)
            db.commit()
        reset_entity_matcher()

    def test_refresh_and_match_uses_distinct_providers(self) -> None:
        canon = "Lake Havasu City BMX"
        with SessionLocal() as db:
            self._ids.append(_insert_program(db, canon))
            self._ids.append(_insert_program(db, canon))
            refresh_entity_matcher(db)
            hit = match_entity("bmx track hours", db)
        self.assertIsNotNone(hit)
        self.assertEqual(hit[0], canon)
