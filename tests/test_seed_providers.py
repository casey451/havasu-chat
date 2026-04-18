"""Phase 1.3 — provider seed from HAVASU_CHAT_MASTER.md Section 9."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.db.database import SessionLocal, init_db
from app.db.models import Event, Program, Provider
from app.db.seed_providers import DEFAULT_MASTER_PATH, _norm_provider_name, seed_providers

MASTER_PATH = Path(__file__).resolve().parents[1] / "HAVASU_CHAT_MASTER.md"


def _clear_providers_and_fks() -> None:
    with SessionLocal() as db:
        for p in db.query(Program).filter(Program.provider_id.isnot(None)):
            p.provider_id = None
        for e in db.query(Event).filter(Event.provider_id.isnot(None)):
            e.provider_id = None
        db.query(Provider).delete()
        db.commit()


class SeedProvidersTests(unittest.TestCase):
    def setUp(self) -> None:
        init_db()
        _clear_providers_and_fks()

    def test_master_path_exists(self) -> None:
        self.assertTrue(MASTER_PATH.is_file(), f"Missing {MASTER_PATH}")

    def test_fresh_db_creates_25_providers(self) -> None:
        with SessionLocal() as db:
            r = seed_providers(db, master_path=MASTER_PATH)
            self.assertEqual(r.created, 25)
            self.assertEqual(r.updated, 0)
            self.assertEqual(r.skipped, 0)
            self.assertEqual(r.total_in_db, 25)
            self.assertEqual(db.query(Provider).count(), 25)

    def test_idempotency_second_run_updates_not_inserts(self) -> None:
        with SessionLocal() as db:
            r1 = seed_providers(db, master_path=MASTER_PATH)
            self.assertEqual(r1.created, 25)
            self.assertEqual(r1.updated, 0)
            iw = (
                db.query(Provider)
                .filter(Provider.provider_name == "Iron Wolf Golf & Country Club")
                .one()
            )
            created_at_first = iw.created_at
            updated_at_first = iw.updated_at
            r2 = seed_providers(db, master_path=MASTER_PATH)
            self.assertEqual(r2.created, 0)
            self.assertEqual(r2.updated, 25)
            self.assertEqual(r2.total_in_db, 25)
            db.refresh(iw)
            self.assertEqual(iw.created_at, created_at_first)
            self.assertGreaterEqual(iw.updated_at, updated_at_first)

    def test_mutation_phone_restored_from_master(self) -> None:
        with SessionLocal() as db:
            seed_providers(db, master_path=MASTER_PATH)
            iw = (
                db.query(Provider)
                .filter(Provider.provider_name == "Iron Wolf Golf & Country Club")
                .one()
            )
            master_phone = iw.phone
            iw.phone = "(999) 999-9999"
            db.commit()
            seed_providers(db, master_path=MASTER_PATH)
            db.refresh(iw)
            self.assertEqual(iw.phone, master_phone)

    def test_elite_cheer_draft_true(self) -> None:
        with SessionLocal() as db:
            seed_providers(db, master_path=MASTER_PATH)
            elite = (
                db.query(Provider)
                .filter(Provider.provider_name == "Elite Cheer Athletics — Havasu")
                .one()
            )
            self.assertTrue(elite.draft)

    def test_category_mapping_spot_checks(self) -> None:
        with SessionLocal() as db:
            seed_providers(db, master_path=MASTER_PATH)
            iron = (
                db.query(Provider)
                .filter(Provider.provider_name == "Iron Wolf Golf & Country Club")
                .one()
            )
            alt = (
                db.query(Provider)
                .filter(
                    Provider.provider_name == "Altitude Trampoline Park — Lake Havasu City"
                )
                .one()
            )
            parks = (
                db.query(Provider)
                .filter(Provider.provider_name == "Lake Havasu City Parks & Recreation")
                .one()
            )
            self.assertEqual(iron.category, "golf")
            self.assertEqual(alt.category, "fitness")
            self.assertEqual(parks.category, "sports")

    def test_default_path_constant_points_at_repo_master(self) -> None:
        self.assertTrue(DEFAULT_MASTER_PATH.is_file())

    def test_norm_provider_name_matches_program_and_canonical_variants(self) -> None:
        """Punctuation + end-anchored suffix fold: same key as short program provider_name."""
        self.assertEqual(
            _norm_provider_name("Altitude Trampoline Park — Lake Havasu City"),
            _norm_provider_name("Altitude Trampoline Park"),
        )
        self.assertEqual(
            _norm_provider_name("Universal Gymnastics and All Star Cheer — Sonics"),
            _norm_provider_name("Universal Gymnastics and All Star Cheer"),
        )
        self.assertEqual(
            _norm_provider_name("Arizona Coast Performing Arts (ACPA)"),
            _norm_provider_name("Arizona Coast Performing Arts"),
        )
        self.assertEqual(
            _norm_provider_name("Iron  Wolf  Golf"),
            _norm_provider_name("iron wolf golf"),
        )
        self.assertEqual(
            _norm_provider_name("O'Brien"),  # curly apostrophe U+2019
            _norm_provider_name("O\u2019Brien"),
        )
