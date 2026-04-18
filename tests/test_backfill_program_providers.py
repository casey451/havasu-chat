"""Phase 1.4 — backfill program.provider_id from providers."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.db.backfill_program_providers import backfill_program_providers
from app.db.database import SessionLocal, init_db
from app.db.models import Program, Provider
from app.db.seed_providers import seed_providers

MASTER_PATH = Path(__file__).resolve().parents[1] / "HAVASU_CHAT_MASTER.md"
_PREFIX = "TEST_BF_BACKFILL_"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _provider(**kwargs: object) -> Provider:
    now = _now()
    defaults: dict = {
        "id": str(uuid4()),
        "category": "golf",
        "tier": "free",
        "sponsored_until": None,
        "featured_description": None,
        "draft": False,
        "verified": False,
        "is_active": True,
        "pending_review": False,
        "admin_review_by": None,
        "source": "seed",
        "created_at": now,
        "updated_at": now,
        "address": None,
        "phone": None,
        "email": None,
        "website": None,
        "facebook": None,
        "hours": None,
        "description": None,
    }
    defaults.update(kwargs)
    return Provider(**defaults)


def _program(**kwargs: object) -> Program:
    now = _now()
    defaults: dict = {
        "title": f"{_PREFIX}title",
        "description": "D" * 25,
        "activity_category": "golf",
        "schedule_days": ["monday"],
        "schedule_start_time": "09:00",
        "schedule_end_time": "10:00",
        "location_name": "Loc",
        "provider_name": f"{_PREFIX}Provider",
        "source": "admin",
        "verified": False,
        "is_active": True,
        "tags": [],
        "embedding": None,
        "provider_id": None,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(kwargs)
    return Program(**defaults)


def _clear_fixtures() -> None:
    with SessionLocal() as db:
        db.query(Program).filter(Program.title.startswith(_PREFIX)).delete(
            synchronize_session=False
        )
        db.query(Program).filter(Program.provider_name.startswith(_PREFIX)).delete(
            synchronize_session=False
        )
        db.query(Provider).filter(Provider.provider_name.startswith(_PREFIX)).delete(
            synchronize_session=False
        )
        db.commit()


class BackfillProgramProvidersTests(unittest.TestCase):
    def setUp(self) -> None:
        init_db()
        _clear_fixtures()

    def tearDown(self) -> None:
        _clear_fixtures()

    def test_exact_match_links(self) -> None:
        name = f"{_PREFIX}Exact Org"
        prov = _provider(provider_name=name)
        prog = _program(title=f"{_PREFIX}e1", provider_name=name)
        with SessionLocal() as db:
            db.add_all([prov, prog])
            db.commit()
            pid = prov.id
            r = backfill_program_providers(db)
            self.assertGreaterEqual(r.linked_exact, 1)
            db.refresh(prog)
            self.assertEqual(prog.provider_id, pid)

    def test_case_whitespace_normalization_exact(self) -> None:
        canonical = f"{_PREFIX}Case Org Name"
        prov = _provider(provider_name=canonical)
        prog = _program(
            title=f"{_PREFIX}c1",
            provider_name=f"{_PREFIX}case  org   name".lower(),
        )
        with SessionLocal() as db:
            db.add_all([prov, prog])
            db.commit()
            r = backfill_program_providers(db)
            self.assertGreaterEqual(r.linked_exact, 1)
            db.refresh(prog)
            self.assertEqual(prog.provider_id, prov.id)

    def test_fuzzy_match_when_truncated(self) -> None:
        full_name = f"{_PREFIX}Fuzzy Target String Long"
        prov = _provider(provider_name=full_name)
        prog = _program(
            title=f"{_PREFIX}f1",
            provider_name=f"{_PREFIX}Fuzzy Target",
        )
        with SessionLocal() as db:
            db.add_all([prov, prog])
            db.commit()
            r = backfill_program_providers(db)
            self.assertGreaterEqual(r.linked_fuzzy, 1)
            self.assertTrue(
                any(d.program_id == prog.id for d in r.fuzzy_details),
                msg=f"expected fuzzy link for fixture program, got {r.fuzzy_details!r}",
            )
            db.refresh(prog)
            self.assertEqual(prog.provider_id, prov.id)

    def test_ambiguous_fuzzy_leaves_unlinked(self) -> None:
        a = _provider(provider_name=f"{_PREFIX}Smith Family Dental")
        b = _provider(provider_name=f"{_PREFIX}Smith Family Gym")
        prog = _program(
            title=f"{_PREFIX}a1",
            provider_name=f"{_PREFIX}Smith Family",
        )
        with SessionLocal() as db:
            db.add_all([a, b, prog])
            db.commit()
            r = backfill_program_providers(db)
            amb_fixture = [a for a in r.ambiguous if a.program_id == prog.id]
            self.assertEqual(len(amb_fixture), 1)
            self.assertEqual(amb_fixture[0].kind, "fuzzy_multiple")
            db.refresh(prog)
            self.assertIsNone(prog.provider_id)

    def test_no_match_reported(self) -> None:
        prov = _provider(provider_name=f"{_PREFIX}Only Provider")
        prog = _program(
            title=f"{_PREFIX}n1",
            provider_name=f"{_PREFIX}Nonexistent Business",
        )
        with SessionLocal() as db:
            db.add_all([prov, prog])
            db.commit()
            r = backfill_program_providers(db)
            self.assertTrue(
                any(pid == prog.id for pid, _ in r.no_match),
                msg=f"expected fixture program in no_match, got {r.no_match!r}",
            )
            db.refresh(prog)
            self.assertIsNone(prog.provider_id)

    def test_skips_already_linked(self) -> None:
        p1 = _provider(provider_name=f"{_PREFIX}Skip A")
        p2 = _provider(provider_name=f"{_PREFIX}Skip B")
        prog = _program(
            title=f"{_PREFIX}s1",
            provider_name=f"{_PREFIX}Skip B",
            provider_id=p1.id,
        )
        with SessionLocal() as db:
            db.add_all([p1, p2, prog])
            db.commit()
            r = backfill_program_providers(db)
            self.assertGreaterEqual(r.skipped_already_linked, 1)
            self.assertEqual(r.programs_updated, 0)
            db.refresh(prog)
            self.assertEqual(prog.provider_id, p1.id)

    def test_idempotency_second_run_updates_zero(self) -> None:
        name = f"{_PREFIX}Idem Org"
        prov = _provider(provider_name=name)
        prog = _program(title=f"{_PREFIX}i1", provider_name=name)
        with SessionLocal() as db:
            db.add_all([prov, prog])
            db.commit()
            r1 = backfill_program_providers(db)
            self.assertGreaterEqual(r1.programs_updated, 1)
            db.refresh(prog)
            self.assertEqual(prog.provider_id, prov.id)
            r2 = backfill_program_providers(db)
            self.assertEqual(r2.programs_updated, 0)
            self.assertGreaterEqual(r2.skipped_already_linked, 1)

    def test_aborts_when_providers_empty(self) -> None:
        self.assertTrue(MASTER_PATH.is_file())
        with SessionLocal() as db:
            for p in db.query(Program).filter(Program.provider_id.isnot(None)):
                p.provider_id = None
            db.query(Provider).delete()
            db.commit()
            prog = _program(title=f"{_PREFIX}empty", provider_name="x")
            db.add(prog)
            db.commit()
            try:
                with self.assertRaises(RuntimeError):
                    backfill_program_providers(db)
            finally:
                db.query(Program).filter(Program.title.startswith(_PREFIX)).delete(
                    synchronize_session=False
                )
                db.commit()
                seed_providers(db, master_path=MASTER_PATH)
