"""Tests for ``Contribution`` ORM (Phase 5.1)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from app.db.database import SessionLocal
from app.db.models import ChatLog, Contribution, Provider


def test_contribution_defaults_on_insert() -> None:
    with SessionLocal() as db:
        row = Contribution(
            entity_type="tip",
            submission_name="Test tip default row",
            submission_notes="notes",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        assert row.id is not None
        assert row.status == "pending"
        assert row.source == "user_submission"
        assert row.unverified is False
        assert row.submitted_at is not None
        db.delete(row)
        db.commit()


def test_contribution_submitted_at_populated() -> None:
    with SessionLocal() as db:
        before = datetime.now(UTC).replace(tzinfo=None).replace(microsecond=0)
        row = Contribution(entity_type="event", submission_name="Timing row")
        db.add(row)
        db.commit()
        db.refresh(row)
        assert row.submitted_at.replace(microsecond=0) >= before
        db.delete(row)
        db.commit()


def test_contribution_foreign_keys_optional() -> None:
    with SessionLocal() as db:
        prov = Provider(
            provider_name="Contrib FK Test Provider",
            category="other",
        )
        db.add(prov)
        db.commit()
        db.refresh(prov)
        pid = prov.id
        log = ChatLog(
            session_id="contrib-model-fk",
            message="user q",
            role="user",
            intent=None,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        row = Contribution(
            entity_type="provider",
            submission_name="FK probe",
            submission_url="https://example.com/fk",
            created_provider_id=pid,
            llm_source_chat_log_id=log.id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        assert row.created_provider_id == pid
        assert row.llm_source_chat_log_id == log.id

        db.delete(row)
        db.delete(log)
        db.delete(prov)
        db.commit()


def test_contribution_event_fields() -> None:
    d = date(2026, 7, 4)
    t0 = time(10, 30)
    t1 = time(12, 0)
    with SessionLocal() as db:
        row = Contribution(
            entity_type="event",
            submission_name="Parade",
            event_date=d,
            event_time_start=t0,
            event_time_end=t1,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        assert row.event_date == d
        assert row.event_time_start == t0
        assert row.event_time_end == t1
        db.delete(row)
        db.commit()


def test_contribution_source_override() -> None:
    with SessionLocal() as db:
        row = Contribution(
            entity_type="tip",
            submission_name="operator row",
            source="operator_backfill",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        assert row.source == "operator_backfill"
        db.delete(row)
        db.commit()
