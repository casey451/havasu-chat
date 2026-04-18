"""Phase 1.5 — populate program concierge fields from HAVASU_CHAT_MASTER.md."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from app.db.database import SessionLocal, init_db
from app.db.models import Program
from app.db.populate_program_concierge_fields import populate_program_concierge_fields

_PREFIX = "TEST_PC_CONCIERGE_"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


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
        "cost": None,
        "location_address": None,
        "contact_phone": None,
        "contact_email": None,
        "contact_url": None,
        "age_min": None,
        "age_max": None,
        "show_pricing_cta": False,
        "cost_description": None,
        "schedule_note": None,
        "draft": False,
        "pending_review": False,
        "admin_review_by": None,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(kwargs)
    return Program(**defaults)


def _clear_fixtures() -> None:
    with SessionLocal() as db:
        db.query(Program).filter(Program.title.startswith(_PREFIX)).delete(synchronize_session=False)
        db.query(Program).filter(Program.provider_name.startswith(_PREFIX)).delete(
            synchronize_session=False
        )
        db.commit()


def _write_master(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


class PopulateProgramConciergeFieldsTests(unittest.TestCase):
    def setUp(self) -> None:
        init_db()
        _clear_fixtures()
        self._tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        _clear_fixtures()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _master_path(self) -> Path:
        return self._tmp / "master.md"

    def _biz_header(self, provider: str) -> str:
        return (
            f"## BUSINESS 900 — {_PREFIX}HEADER\n\n"
            "```\n"
            f"provider_name:    {provider}\n"
            "category:         golf\n"
            "```\n\n"
            "### Programs\n\n"
        )

    def test_contact_for_pricing_sets_show_cta_only(self) -> None:
        prov = f"{_PREFIX}Org A"
        title = f"{_PREFIX}Contact Session"
        master = (
            self._biz_header(prov)
            + "```yaml\n"
            + f"- title:              {title}\n"
            + "  activity_category:  golf\n"
            + "  schedule_days:      [MON]\n"
            + "  schedule_start_time: \"09:00\"\n"
            + "  schedule_end_time:   \"10:00\"\n"
            + "  location_name:      Here\n"
            + "  cost:               CONTACT_FOR_PRICING\n"
            + "  cost_description:   \"$99 should be ignored for CONTACT\"\n"
            + f"  provider_name:      {prov}\n"
            + "  description:        " + ("x" * 20) + "\n"
            + "```\n"
        )
        mp = self._master_path()
        _write_master(mp, master)
        prog = _program(title=title, provider_name=prov)
        with SessionLocal() as db:
            db.add(prog)
            db.commit()
            r = populate_program_concierge_fields(db, master_path=mp)
            self.assertEqual(r.programs_updated, 1)
            self.assertEqual(r.set_show_pricing_cta, 1)
            self.assertEqual(r.set_cost_description, 0)
            db.refresh(prog)
            self.assertTrue(prog.show_pricing_cta)
            self.assertIsNone(prog.cost_description)

    def test_cost_description_populated_when_present(self) -> None:
        prov = f"{_PREFIX}Org B"
        title = f"{_PREFIX}Priced Session"
        note = "$37 per session (confirm current rate)"
        master = (
            self._biz_header(prov)
            + "```yaml\n"
            + f"- title:              {title}\n"
            + "  activity_category:  golf\n"
            + "  schedule_days:      [MON]\n"
            + "  schedule_start_time: \"09:00\"\n"
            + "  schedule_end_time:   \"10:00\"\n"
            + "  location_name:      Here\n"
            + "  cost:               37.00\n"
            + f"  cost_description:   \"{note}\"\n"
            + f"  provider_name:      {prov}\n"
            + "  description:        " + ("y" * 20) + "\n"
            + "```\n"
        )
        mp = self._master_path()
        _write_master(mp, master)
        prog = _program(title=title, provider_name=prov)
        with SessionLocal() as db:
            db.add(prog)
            db.commit()
            r = populate_program_concierge_fields(db, master_path=mp)
            self.assertEqual(r.set_cost_description, 1)
            db.refresh(prog)
            self.assertEqual(prog.cost_description, note)
            self.assertFalse(prog.show_pricing_cta)

    def test_schedule_note_verbatim(self) -> None:
        prov = f"{_PREFIX}Org C"
        title = f"{_PREFIX}Schedule Session"
        sn = "Mon–Fri evenings. ⚠️ VERIFY times."
        master = (
            self._biz_header(prov)
            + "```yaml\n"
            + f"- title:              {title}\n"
            + "  activity_category:  golf\n"
            + "  schedule_days:      [MON]\n"
            + "  schedule_start_time: \"09:00\"\n"
            + "  schedule_end_time:   \"10:00\"\n"
            + "  location_name:      Here\n"
            + f"  schedule_note:      \"{sn}\"\n"
            + "  cost:               10.00\n"
            + f"  provider_name:      {prov}\n"
            + "  description:        " + ("z" * 20) + "\n"
            + "```\n"
        )
        mp = self._master_path()
        _write_master(mp, master)
        prog = _program(title=title, provider_name=prov)
        with SessionLocal() as db:
            db.add(prog)
            db.commit()
            r = populate_program_concierge_fields(db, master_path=mp)
            self.assertEqual(r.set_schedule_note, 1)
            db.refresh(prog)
            self.assertEqual(prog.schedule_note, sn)

    def test_draft_true_from_master(self) -> None:
        prov = f"{_PREFIX}Org D"
        title = f"{_PREFIX}Draft Session"
        master = (
            self._biz_header(prov)
            + "```yaml\n"
            + f"- title:              {title}\n"
            + "  activity_category:  cheer\n"
            + "  schedule_days:      [MON]\n"
            + "  schedule_start_time: \"09:00\"\n"
            + "  schedule_end_time:   \"10:00\"\n"
            + "  location_name:      Here\n"
            + "  draft:              true\n"
            + "  cost:               CONTACT_FOR_PRICING\n"
            + f"  provider_name:      {prov}\n"
            + "  description:        " + ("w" * 20) + "\n"
            + "```\n"
        )
        mp = self._master_path()
        _write_master(mp, master)
        prog = _program(title=title, provider_name=prov, activity_category="cheer")
        with SessionLocal() as db:
            db.add(prog)
            db.commit()
            r = populate_program_concierge_fields(db, master_path=mp)
            self.assertEqual(r.set_draft, 1)
            db.refresh(prog)
            self.assertTrue(prog.draft)

    def test_no_match_leaves_defaults(self) -> None:
        prov = f"{_PREFIX}Org E"
        master = (
            self._biz_header(prov)
            + "```yaml\n"
            + f"- title:              {_PREFIX}Only In Master\n"
            + "  activity_category:  golf\n"
            + "  schedule_days:      [MON]\n"
            + "  schedule_start_time: \"09:00\"\n"
            + "  schedule_end_time:   \"10:00\"\n"
            + "  location_name:      Here\n"
            + "  cost:               1.00\n"
            + f"  provider_name:      {prov}\n"
            + "  description:        " + ("q" * 20) + "\n"
            + "```\n"
        )
        mp = self._master_path()
        _write_master(mp, master)
        prog = _program(title=f"{_PREFIX}Not In Master", provider_name=prov)
        with SessionLocal() as db:
            db.add(prog)
            db.commit()
            r = populate_program_concierge_fields(db, master_path=mp)
            self.assertEqual(r.programs_updated, 0)
            self.assertTrue(
                any(pid == prog.id for pid, _, _ in r.programs_no_match),
                msg=f"expected fixture program in no_match, got {len(r.programs_no_match)} rows",
            )
            db.refresh(prog)
            self.assertFalse(prog.show_pricing_cta)
            self.assertIsNone(prog.cost_description)

    def test_skips_when_show_pricing_cta_already_set(self) -> None:
        prov = f"{_PREFIX}Org F"
        title = f"{_PREFIX}Protected Cta"
        master = (
            self._biz_header(prov)
            + "```yaml\n"
            + f"- title:              {title}\n"
            + "  activity_category:  golf\n"
            + "  schedule_days:      [MON]\n"
            + "  schedule_start_time: \"09:00\"\n"
            + "  schedule_end_time:   \"10:00\"\n"
            + "  location_name:      Here\n"
            + "  cost:               CONTACT_FOR_PRICING\n"
            + f"  provider_name:      {prov}\n"
            + "  description:        " + ("v" * 20) + "\n"
            + "```\n"
        )
        mp = self._master_path()
        _write_master(mp, master)
        prog = _program(title=title, provider_name=prov, show_pricing_cta=True)
        with SessionLocal() as db:
            db.add(prog)
            db.commit()
            r = populate_program_concierge_fields(db, master_path=mp)
            self.assertEqual(r.programs_skipped_intervention, 1)
            self.assertEqual(r.programs_updated, 0)
            db.refresh(prog)
            self.assertTrue(prog.show_pricing_cta)
            self.assertIsNone(prog.cost_description)

    def test_skips_when_schedule_note_already_set(self) -> None:
        prov = f"{_PREFIX}Org G"
        title = f"{_PREFIX}Protected Schedule"
        existing = "already set by admin"
        master = (
            self._biz_header(prov)
            + "```yaml\n"
            + f"- title:              {title}\n"
            + "  activity_category:  golf\n"
            + "  schedule_days:      [MON]\n"
            + "  schedule_start_time: \"09:00\"\n"
            + "  schedule_end_time:   \"10:00\"\n"
            + "  location_name:      Here\n"
            + "  schedule_note:      \"master says different\"\n"
            + "  cost:               5.00\n"
            + f"  provider_name:      {prov}\n"
            + "  description:        " + ("t" * 20) + "\n"
            + "```\n"
        )
        mp = self._master_path()
        _write_master(mp, master)
        prog = _program(title=title, provider_name=prov, schedule_note=existing)
        with SessionLocal() as db:
            db.add(prog)
            db.commit()
            r = populate_program_concierge_fields(db, master_path=mp)
            self.assertEqual(r.programs_skipped_intervention, 1)
            db.refresh(prog)
            self.assertEqual(prog.schedule_note, existing)

    def test_idempotency_second_run_no_updates(self) -> None:
        prov = f"{_PREFIX}Org H"
        title = f"{_PREFIX}Idem Session"
        master = (
            self._biz_header(prov)
            + "```yaml\n"
            + f"- title:              {title}\n"
            + "  activity_category:  golf\n"
            + "  schedule_days:      [MON]\n"
            + "  schedule_start_time: \"09:00\"\n"
            + "  schedule_end_time:   \"10:00\"\n"
            + "  location_name:      Here\n"
            + "  cost:               CONTACT_FOR_PRICING\n"
            + f"  provider_name:      {prov}\n"
            + "  description:        " + ("u" * 20) + "\n"
            + "```\n"
        )
        mp = self._master_path()
        _write_master(mp, master)
        prog = _program(title=title, provider_name=prov)
        with SessionLocal() as db:
            db.add(prog)
            db.commit()
            r1 = populate_program_concierge_fields(db, master_path=mp)
            self.assertEqual(r1.programs_updated, 1)
            r2 = populate_program_concierge_fields(db, master_path=mp)
            self.assertEqual(r2.programs_updated, 0)
            self.assertGreaterEqual(r2.programs_skipped_intervention, 1)

    def test_malformed_program_yaml_raises_runtime_error(self) -> None:
        """Parse failures in master ### Programs YAML must halt — not silent no-match."""
        prov = f"{_PREFIX}BadYamlOrg"
        master = (
            self._biz_header(prov)
            + "```yaml\n"
            + "- title:              Malformed Row\n"
            + "  activity_category:  golf\n"
            + "  schedule_days:      [MON]\n"
            + "  schedule_start_time: \"09:00\"\n"
            + "  schedule_end_time:   \"10:00\"\n"
            + "  location_name:      Here\n"
            + "  cost:               1.00\n"
            + f"  provider_name:      {prov}\n"
            + "  description:        unquoted: colon breaks yaml\n"
            + "```\n"
        )
        mp = self._master_path()
        _write_master(mp, master)
        with SessionLocal() as db:
            with self.assertRaises(RuntimeError) as ctx:
                populate_program_concierge_fields(db, master_path=mp)
        msg = str(ctx.exception)
        self.assertIn("YAML parse failed", msg)
        self.assertIn("HAVASU_CHAT_MASTER.md", msg)
        self.assertIn("business section", msg)
