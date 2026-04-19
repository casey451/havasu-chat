"""Phase 1.7 — field_history established baseline seed."""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime, time
from uuid import uuid4

from sqlalchemy import select

from app.core.field_tracking import (
    EVENT_TRACKED_FIELDS,
    PROGRAM_TRACKED_FIELDS,
    PROVIDER_TRACKED_FIELDS,
)
from app.db.database import SessionLocal, init_db
from app.db.models import Event, FieldHistory, Program, Provider
from app.db.seed_field_history_baseline import seed_field_history_baseline

_PREFIX = "TEST_FH_"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _provider(**kwargs: object) -> Provider:
    now = _now()
    defaults: dict = {
        "id": str(uuid4()),
        "provider_name": f"{_PREFIX}Org",
        "category": "sports",
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
        "address": "123 Main St",
        "phone": "9285550100",
        "email": "info@example.com",
        "website": "https://example.com",
        "facebook": None,
        "hours": "Mon–Fri 9–5",
        "description": None,
    }
    defaults.update(kwargs)
    return Provider(**defaults)


def _program(**kwargs: object) -> Program:
    now = _now()
    defaults: dict = {
        "id": str(uuid4()),
        "title": f"{_PREFIX}Prog",
        "description": "D" * 25,
        "activity_category": "sports",
        "age_min": None,
        "age_max": 12,
        "schedule_days": ["monday"],
        "schedule_start_time": "09:00",
        "schedule_end_time": "10:00",
        "location_name": "Here",
        "location_address": None,
        "cost": "CONTACT_FOR_PRICING",
        "provider_name": f"{_PREFIX}Org",
        "contact_phone": "9285550101",
        "contact_email": None,
        "contact_url": None,
        "source": "admin",
        "verified": False,
        "is_active": True,
        "tags": [],
        "embedding": None,
        "provider_id": None,
        "created_at": now,
        "updated_at": now,
        "show_pricing_cta": False,
        "cost_description": None,
        "schedule_note": "Afternoons",
        "draft": False,
        "pending_review": False,
        "admin_review_by": None,
    }
    defaults.update(kwargs)
    return Program(**defaults)


def _event(**kwargs: object) -> Event:
    now = _now()
    t = f"{_PREFIX}Evt"
    loc = "Aquatic Center"
    defaults: dict = {
        "id": str(uuid4()),
        "title": t,
        "normalized_title": t.lower(),
        "date": date(2026, 7, 4),
        "start_time": time(18, 0),
        "end_time": time(21, 0),
        "location_name": loc,
        "location_normalized": loc.lower(),
        "description": "E" * 25,
        "event_url": "https://example.com/e",
        "contact_name": None,
        "contact_phone": None,
        "tags": [],
        "embedding": None,
        "status": "live",
        "source": "admin",
        "verified": False,
        "created_at": now,
        "created_by": "test",
        "admin_review_by": None,
        "provider_id": None,
    }
    defaults.update(kwargs)
    return Event(**defaults)


def _clear_field_history_fixture_rows() -> None:
    with SessionLocal() as db:
        pr_ids = [r[0] for r in db.execute(select(Provider.id).where(Provider.provider_name.startswith(_PREFIX))).all()]
        p_ids = [r[0] for r in db.execute(select(Program.id).where(Program.title.startswith(_PREFIX))).all()]
        e_ids = [r[0] for r in db.execute(select(Event.id).where(Event.title.startswith(_PREFIX))).all()]
        for eid in pr_ids + p_ids + e_ids:
            db.query(FieldHistory).filter(FieldHistory.entity_id == eid).delete(synchronize_session=False)
        db.query(Program).filter(Program.title.startswith(_PREFIX)).delete(synchronize_session=False)
        db.query(Event).filter(Event.title.startswith(_PREFIX)).delete(synchronize_session=False)
        db.query(Provider).filter(Provider.provider_name.startswith(_PREFIX)).delete(synchronize_session=False)
        db.commit()


class SeedFieldHistoryBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        init_db()
        _clear_field_history_fixture_rows()

    def tearDown(self) -> None:
        _clear_field_history_fixture_rows()

    def test_fresh_db_creates_one_established_row_per_tracked_field(self) -> None:
        prov = _provider()
        prog = _program(provider_name=prov.provider_name)
        ev = _event()
        exp = len(PROVIDER_TRACKED_FIELDS) + len(PROGRAM_TRACKED_FIELDS) + len(EVENT_TRACKED_FIELDS)
        our_ids = {prov.id, prog.id, ev.id}
        with SessionLocal() as db:
            db.add_all([prov, prog, ev])
            db.commit()
            seed_field_history_baseline(db)
            n = (
                db.query(FieldHistory)
                .filter(
                    FieldHistory.entity_id.in_(our_ids),
                    FieldHistory.state == "established",
                    FieldHistory.source == "seed",
                )
                .count()
            )
            self.assertEqual(n, exp)

    def test_scalar_string_not_json_wrapped(self) -> None:
        prov = _provider(phone="9285559999")
        with SessionLocal() as db:
            db.add(prov)
            db.commit()
            seed_field_history_baseline(db)
            row = (
                db.query(FieldHistory)
                .filter(
                    FieldHistory.entity_id == prov.id,
                    FieldHistory.field_name == "phone",
                    FieldHistory.state == "established",
                )
                .one()
            )
            self.assertEqual(row.new_value, "9285559999")
            self.assertFalse(row.new_value.startswith('"') and row.new_value.endswith('"'))

    def test_null_entity_field_stores_null_new_value(self) -> None:
        prov = _provider(phone=None)
        with SessionLocal() as db:
            db.add(prov)
            db.commit()
            seed_field_history_baseline(db)
            row = (
                db.query(FieldHistory)
                .filter(
                    FieldHistory.entity_id == prov.id,
                    FieldHistory.field_name == "phone",
                    FieldHistory.state == "established",
                )
                .one()
            )
            self.assertIsNone(row.new_value)

    def test_program_cost_scalar_stored_plain(self) -> None:
        prog = _program(schedule_days=["tue", "wed"])
        with SessionLocal() as db:
            db.add(prog)
            db.commit()
            seed_field_history_baseline(db)
            row = (
                db.query(FieldHistory)
                .filter(
                    FieldHistory.entity_id == prog.id,
                    FieldHistory.field_name == "cost",
                    FieldHistory.state == "established",
                )
                .one()
            )
            self.assertEqual(row.new_value, "CONTACT_FOR_PRICING")

    def test_idempotency_second_run_all_skipped(self) -> None:
        prov = _provider()
        exp = len(PROVIDER_TRACKED_FIELDS)
        with SessionLocal() as db:
            db.add(prov)
            db.commit()
            seed_field_history_baseline(db)
            c1 = (
                db.query(FieldHistory)
                .filter(FieldHistory.entity_id == prov.id, FieldHistory.state == "established")
                .count()
            )
            self.assertEqual(c1, exp)
            seed_field_history_baseline(db)
            c2 = (
                db.query(FieldHistory)
                .filter(FieldHistory.entity_id == prov.id, FieldHistory.state == "established")
                .count()
            )
            self.assertEqual(c2, c1)

    def test_resolved_row_untouched_and_baseline_not_duplicated(self) -> None:
        prov = _provider()
        prog = _program(cost="10.00", provider_name=prov.provider_name)
        with SessionLocal() as db:
            db.add_all([prov, prog])
            db.commit()
            pid = prog.id
            fh_res = FieldHistory(
                id=str(uuid4()),
                entity_type="program",
                entity_id=pid,
                field_name="cost",
                old_value='"5.00"',
                new_value='"10.00"',
                source="user",
                submitted_by_session="sess",
                submitted_at=_now(),
                state="resolved",
                confirmations=1,
                disputes=0,
                resolution_deadline=None,
                resolved_at=_now(),
                resolved_value='"10.00"',
                resolution_source="admin",
            )
            db.add(fh_res)
            db.commit()
            before_resolved = (
                db.query(FieldHistory)
                .filter(FieldHistory.id == fh_res.id, FieldHistory.state == "resolved")
                .one()
            )
            resolved_snapshot = (
                before_resolved.resolved_value,
                before_resolved.new_value,
                before_resolved.confirmations,
            )

            r = seed_field_history_baseline(db)
            self.assertGreaterEqual(r.rows_created_program, 1)
            db.refresh(before_resolved)
            self.assertEqual(
                (before_resolved.resolved_value, before_resolved.new_value, before_resolved.confirmations),
                resolved_snapshot,
            )
            established = (
                db.query(FieldHistory)
                .filter(
                    FieldHistory.entity_id == pid,
                    FieldHistory.field_name == "cost",
                    FieldHistory.state == "established",
                )
                .all()
            )
            self.assertEqual(len(established), 1)
            self.assertEqual(established[0].new_value, "10.00")

    def test_existing_established_skipped_not_updated(self) -> None:
        prov = _provider(phone="1111111111")
        with SessionLocal() as db:
            db.add(prov)
            db.commit()
            seed_field_history_baseline(db)
            db.query(Provider).filter(Provider.id == prov.id).update({"phone": "2222222222"})
            db.commit()
            r2 = seed_field_history_baseline(db)
            self.assertGreaterEqual(r2.rows_skipped, 1)
            row = (
                db.query(FieldHistory)
                .filter(
                    FieldHistory.entity_id == prov.id,
                    FieldHistory.field_name == "phone",
                    FieldHistory.state == "established",
                )
                .one()
            )
            self.assertEqual(row.new_value, "1111111111")

    def test_entities_not_mutated(self) -> None:
        prov = _provider()
        with SessionLocal() as db:
            db.add(prov)
            db.commit()
            db.refresh(prov)
            ua = prov.updated_at
            seed_field_history_baseline(db)
            db.refresh(prov)
            self.assertEqual(prov.updated_at, ua)


if __name__ == "__main__":
    unittest.main()
