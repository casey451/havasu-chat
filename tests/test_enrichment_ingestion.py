"""Tests for the operator enrichment validator + ingest pipeline.

Covers:

* Validator rejects: missing columns, bad phone, unknown category,
  empty address, future ``last_verified_at``, too-short / too-long
  description, bad email, unknown ``verification_method``.
* Validator accepts a known-good row.
* Ingest inserts a new Provider correctly.
* Ingest updates an existing Provider correctly (idempotent — the
  second run is a no-op).
* ``--dry-run`` does not commit.

Uses the session-scoped sqlite test DB from ``tests/conftest.py``.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.models import Provider
from scripts.ingest.ingest_enrichment_csv import run as ingest_run
from scripts.ingest.validate_enrichment_csv import (
    REQUIRED_COLUMNS,
    validate_csv,
    validate_row,
)

# ─────────── helpers ───────────


_GOOD_ROW: dict[str, str] = {
    "provider_name": "Havasu Pool Pros",
    "category": "home-property-services",
    "address": "2200 N McCulloch Blvd, Lake Havasu City, AZ 86403",
    "phone": "(928) 444-0133",  # 555-01XX is a placeholder; use 444 instead
    "owner_email": "owner@havasupoolpros.example",
    "website": "https://havasupoolpros.example",
    "hours": "Mon-Fri 8am-5pm",
    "hava_voice_description": (
        "Local pool techs who know hard-water Havasu chemistry cold. "
        "They handle weekly service, green-to-clean rescues, and "
        "equipment repair across the south end of the lake."
    ),
    "last_verified_at": "2026-05-08T09:30:00-07:00",
    "verification_method": "phone_call",
}


def _write_csv(
    path: Path,
    rows: list[dict[str, str]],
    *,
    columns: tuple[str, ...] | None = None,
) -> Path:
    cols = columns if columns is not None else tuple(_GOOD_ROW.keys())
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=cols)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in cols})
    return path


def _good_row(**overrides: Any) -> dict[str, str]:
    row = dict(_GOOD_ROW)
    row.update({k: v for k, v in overrides.items()})
    return row


# ─────────── per-row validator unit tests ───────────


def test_validate_row_accepts_good_row() -> None:
    result = validate_row(_good_row(), row_number=2)
    assert result.passed, result.errors


def test_validate_row_rejects_bad_phone() -> None:
    result = validate_row(_good_row(phone="123"), row_number=2)
    assert not result.passed
    assert any("phone" in e for e in result.errors)


def test_validate_row_rejects_placeholder_phone() -> None:
    # 928-555-0123 is a NANP-reserved placeholder.
    result = validate_row(_good_row(phone="9285550123"), row_number=2)
    assert not result.passed
    assert any("placeholder" in e.lower() for e in result.errors)


def test_validate_row_rejects_unknown_category() -> None:
    result = validate_row(_good_row(category="space_pirates"), row_number=2)
    assert not result.passed
    assert any("category" in e for e in result.errors)


def test_validate_row_rejects_empty_address() -> None:
    result = validate_row(_good_row(address=""), row_number=2)
    assert not result.passed
    assert any("address" in e for e in result.errors)


def test_validate_row_rejects_future_last_verified_at() -> None:
    future = (datetime.now(UTC) + timedelta(days=365)).isoformat()
    result = validate_row(_good_row(last_verified_at=future), row_number=2)
    assert not result.passed
    assert any("future" in e for e in result.errors)


def test_validate_row_rejects_short_description() -> None:
    result = validate_row(_good_row(hava_voice_description="too short"), row_number=2)
    assert not result.passed
    assert any("hava_voice_description" in e for e in result.errors)


def test_validate_row_rejects_long_description() -> None:
    result = validate_row(
        _good_row(hava_voice_description="x" * 401), row_number=2
    )
    assert not result.passed
    assert any("hava_voice_description" in e for e in result.errors)


def test_validate_row_rejects_bad_email() -> None:
    result = validate_row(_good_row(owner_email="not-an-email"), row_number=2)
    assert not result.passed
    assert any("email" in e for e in result.errors)


def test_validate_row_rejects_unknown_verification_method() -> None:
    result = validate_row(_good_row(verification_method="carrier_pigeon"), row_number=2)
    assert not result.passed
    assert any("verification_method" in e for e in result.errors)


# ─────────── file-level validator tests ───────────


def test_validate_csv_rejects_missing_required_column(tmp_path: Path) -> None:
    # Drop a required column from the header.
    cols = tuple(c for c in REQUIRED_COLUMNS if c != "owner_email")
    path = _write_csv(tmp_path / "missing.csv", [_good_row()], columns=cols)
    report = validate_csv(path)
    assert not report.ok
    assert any("owner_email" in msg for msg in report.fatal)


def test_validate_csv_accepts_good_row(tmp_path: Path) -> None:
    path = _write_csv(tmp_path / "good.csv", [_good_row()])
    report = validate_csv(path)
    assert report.ok, [r.errors for r in report.rows] + report.fatal


# ─────────── DB-backed ingest tests ───────────


def _delete_provider_by_name(name: str) -> None:
    """Test cleanup helper — remove any provider rows we created."""
    with SessionLocal() as db:
        rows = db.query(Provider).filter(Provider.provider_name == name).all()
        for r in rows:
            db.delete(r)
        db.commit()


@pytest.fixture
def isolated_provider() -> Any:
    """Make sure the test name isn't lingering before/after a test."""
    name = _GOOD_ROW["provider_name"]
    _delete_provider_by_name(name)
    yield name
    _delete_provider_by_name(name)


def test_ingest_inserts_new_provider(tmp_path: Path, isolated_provider: str) -> None:
    path = _write_csv(tmp_path / "ingest_insert.csv", [_good_row()])
    rc = ingest_run(path, dry_run=False)
    assert rc == 0

    with SessionLocal() as db:
        rows = (
            db.query(Provider)
            .filter(Provider.provider_name == isolated_provider)
            .all()
        )
        assert len(rows) == 1
        p = rows[0]
        assert p.category == "home-property-services"
        assert p.phone == "9284440133"
        assert p.email == "owner@havasupoolpros.example"
        assert p.verification_method == "phone_call"
        assert p.last_verified_at is not None
        # TZAwareDateTime always returns aware datetimes in LAKE_HAVASU_TZ.
        assert p.last_verified_at.tzinfo is not None
        assert p.last_verified_at.utcoffset() == LAKE_HAVASU_TZ.utcoffset(
            datetime(2026, 5, 8)
        )


def test_ingest_updates_existing_provider_idempotently(
    tmp_path: Path, isolated_provider: str
) -> None:
    path = _write_csv(tmp_path / "ingest_upsert.csv", [_good_row()])

    # First run — INSERT.
    rc1 = ingest_run(path, dry_run=False)
    assert rc1 == 0

    # Second run with the SAME csv — should be SKIP-NOOP, still rc 0.
    rc2 = ingest_run(path, dry_run=False)
    assert rc2 == 0

    # Now mutate one field and re-run — should UPDATE.
    new_addr = "9999 Updated Way, Lake Havasu City, AZ 86403"
    path2 = _write_csv(
        tmp_path / "ingest_upsert2.csv", [_good_row(address=new_addr)]
    )
    rc3 = ingest_run(path2, dry_run=False)
    assert rc3 == 0

    with SessionLocal() as db:
        rows = (
            db.query(Provider)
            .filter(Provider.provider_name == isolated_provider)
            .all()
        )
        assert len(rows) == 1, "upsert must not create duplicates"
        assert rows[0].address == new_addr


def test_ingest_dry_run_does_not_commit(
    tmp_path: Path, isolated_provider: str
) -> None:
    path = _write_csv(tmp_path / "ingest_dry.csv", [_good_row()])
    rc = ingest_run(path, dry_run=True)
    assert rc == 0

    with SessionLocal() as db:
        rows = (
            db.query(Provider)
            .filter(Provider.provider_name == isolated_provider)
            .all()
        )
        assert rows == [], "dry-run must not commit any rows"


def test_ingest_refuses_when_validation_fails(
    tmp_path: Path, isolated_provider: str
) -> None:
    bad = _good_row(phone="123")
    path = _write_csv(tmp_path / "ingest_bad.csv", [bad])
    rc = ingest_run(path, dry_run=False)
    assert rc == 1

    with SessionLocal() as db:
        rows = (
            db.query(Provider)
            .filter(Provider.provider_name == isolated_provider)
            .all()
        )
        assert rows == [], "validation failure must block any DB writes"
