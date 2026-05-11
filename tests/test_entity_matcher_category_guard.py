"""Backlog #47 — cross-category guard for ``match_entity`` (plumber vs BMX)."""

from __future__ import annotations

import unittest

from sqlalchemy import delete

from app.chat.entity_matcher import match_entity, refresh_entity_matcher, reset_entity_matcher
from app.db.database import SessionLocal
from app.db.models import Program, Provider
from tests.test_entity_matcher import _insert_program

_CANON_BMX = "Lake Havasu City BMX"


class CategoryGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_entity_matcher()
        self._ids: list[str] = []
        # Full-suite order can leave other rows with the same canonical — scrub so
        # ``refresh_entity_matcher`` indexes exactly what this module inserts.
        with SessionLocal() as db:
            db.execute(delete(Program).where(Program.provider_name == _CANON_BMX))
            db.execute(delete(Provider).where(Provider.provider_name == _CANON_BMX))
            db.commit()

    def tearDown(self) -> None:
        with SessionLocal() as db:
            for pid in self._ids:
                row = db.get(Program, pid)
                if row is not None:
                    db.delete(row)
            db.execute(delete(Program).where(Program.provider_name == _CANON_BMX))
            db.execute(delete(Provider).where(Provider.provider_name == _CANON_BMX))
            db.commit()
        reset_entity_matcher()

    def test_plumber_open_ended_query_does_not_resolve_to_bmx(self) -> None:
        canon = _CANON_BMX
        with SessionLocal() as db:
            self._ids.append(_insert_program(db, canon))
            refresh_entity_matcher(db)
            hit = match_entity("what is the best plumber in lake havasu", db)
        self.assertTrue(hit is None or hit[0] != canon, msg=repr(hit))

    def test_best_plumber_query_no_bmx_sibling_cases(self) -> None:
        canon = _CANON_BMX
        queries = (
            "who is the best plumber around lake havasu",
            "find me a plumbing contractor in lake havasu city",
            "top rated plumber lake havasu az",
        )
        with SessionLocal() as db:
            self._ids.append(_insert_program(db, canon))
            refresh_entity_matcher(db)
            for q in queries:
                with self.subTest(q=q):
                    hit = match_entity(q, db)
                    self.assertTrue(hit is None or hit[0] != canon, msg=repr(hit))

    def test_electrician_open_ended_vs_bmx(self) -> None:
        canon = _CANON_BMX
        with SessionLocal() as db:
            self._ids.append(_insert_program(db, canon))
            refresh_entity_matcher(db)
            hit = match_entity("need an electrician in lake havasu city today", db)
        self.assertTrue(hit is None or hit[0] != canon, msg=repr(hit))

    def test_explicit_bmx_hours_query_still_matches(self) -> None:
        canon = _CANON_BMX
        with SessionLocal() as db:
            self._ids.append(_insert_program(db, canon))
            refresh_entity_matcher(db)
            hit = match_entity("hours for Lake Havasu City BMX", db)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], canon)

    def test_bmx_alias_query_still_matches(self) -> None:
        canon = _CANON_BMX
        with SessionLocal() as db:
            self._ids.append(_insert_program(db, canon))
            refresh_entity_matcher(db)
            hit = match_entity("bmx track practice schedule lake havasu", db)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], canon)


if __name__ == "__main__":
    unittest.main()
