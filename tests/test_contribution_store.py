"""Tests for ``contribution_store`` (Phase 5.1)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.db.contribution_store import (
    create_contribution,
    get_contribution,
    list_contributions,
    update_contribution_status,
)
from app.db.database import SessionLocal
from app.db.models import Provider
from app.schemas.contribution import ContributionCreate


def test_create_contribution_sets_fields() -> None:
    with SessionLocal() as db:
        data = ContributionCreate(
            entity_type="tip",
            submission_name="Store create probe",
            submission_notes="hello",
            source="operator_backfill",
        )
        row = create_contribution(db, data, submitter_ip_hash=None)
        assert row.id is not None
        assert row.submission_name == "Store create probe"
        assert row.status == "pending"
        assert row.source == "operator_backfill"
        db.delete(row)
        db.commit()


def test_create_contribution_with_ip_hash() -> None:
    h = "a" * 64
    with SessionLocal() as db:
        data = ContributionCreate(
            entity_type="tip",
            submission_name="IP hash row",
            source="operator_backfill",
        )
        row = create_contribution(db, data, submitter_ip_hash=h)
        assert row.submitter_ip_hash == h
        db.delete(row)
        db.commit()


def test_get_contribution_found_and_missing() -> None:
    with SessionLocal() as db:
        data = ContributionCreate(
            entity_type="tip",
            submission_name="get by id",
            source="operator_backfill",
        )
        row = create_contribution(db, data)
        got = get_contribution(db, row.id)
        assert got is not None
        assert got.id == row.id
        assert get_contribution(db, 999_999_999) is None
        db.delete(row)
        db.commit()


def test_list_contributions_no_filters() -> None:
    with SessionLocal() as db:
        data = ContributionCreate(
            entity_type="tip",
            submission_name="list A",
            source="operator_backfill",
        )
        a = create_contribution(db, data)
        data2 = ContributionCreate(
            entity_type="tip",
            submission_name="list B",
            source="operator_backfill",
        )
        b = create_contribution(db, data2)
        rows = list_contributions(db, limit=100, offset=0)
        ids = {r.id for r in rows}
        assert a.id in ids and b.id in ids
        db.delete(a)
        db.delete(b)
        db.commit()


def test_list_contributions_status_filter() -> None:
    with SessionLocal() as db:
        data = ContributionCreate(
            entity_type="tip",
            submission_name="status filter row",
            source="operator_backfill",
        )
        row = create_contribution(db, data)
        update_contribution_status(db, row.id, "approved")
        rows = list_contributions(db, status="approved", limit=50)
        assert all(r.status == "approved" for r in rows)
        assert any(r.id == row.id for r in rows)
        db.delete(row)
        db.commit()


def test_list_contributions_entity_type_filter() -> None:
    with SessionLocal() as db:
        prov = Provider(provider_name="Store entity-type provider", category="other")
        db.add(prov)
        db.commit()
        data = ContributionCreate(
            entity_type="provider",
            submission_name="typed row",
            submission_url="https://example.com/p/store-entity-filter",
            source="operator_backfill",
        )
        row = create_contribution(db, data)
        rows = list_contributions(db, entity_type="provider", limit=50)
        assert any(r.id == row.id for r in rows)
        db.delete(row)
        db.delete(prov)
        db.commit()


def test_update_contribution_status_sets_reviewed_at() -> None:
    with SessionLocal() as db:
        row = create_contribution(
            db,
            ContributionCreate(
                entity_type="tip",
                submission_name="review ts",
                source="operator_backfill",
            ),
        )
        assert row.reviewed_at is None
        updated = update_contribution_status(db, row.id, "approved", review_notes="ok")
        assert updated is not None
        assert updated.status == "approved"
        assert updated.reviewed_at is not None
        db.delete(updated)
        db.commit()


def test_update_contribution_status_missing_returns_none() -> None:
    with SessionLocal() as db:
        assert update_contribution_status(db, 999_999_999, "approved") is None


def test_update_contribution_status_invalid_raises() -> None:
    with SessionLocal() as db:
        row = create_contribution(
            db,
            ContributionCreate(
                entity_type="tip",
                submission_name="bad status",
                source="operator_backfill",
            ),
        )
        with pytest.raises(ValueError, match="Invalid status"):
            update_contribution_status(db, row.id, "not_a_status")
        db.delete(row)
        db.commit()
