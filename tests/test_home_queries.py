"""Tests for ``app.home.queries``."""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import Provider
from app.home.queries import _format_phone

# --- Fix #3 (placeholder phones) ---


def test_format_phone_strips_placeholder_nanp() -> None:
    assert _format_phone("(928) 555-0100") == (None, None)


def test_format_phone_strips_placeholder_other_areacode() -> None:
    assert _format_phone("(212) 555-0199") == (None, None)


def test_format_phone_keeps_real_number() -> None:
    assert _format_phone("(928) 855-1234") == ("(928) 855-1234", "9288551234")


def test_format_phone_keeps_real_555_outside_01xx() -> None:
    assert _format_phone("(928) 555-1234") == ("(928) 555-1234", "9285551234")


def test_format_phone_handles_already_digits() -> None:
    assert _format_phone("9285550100") == (None, None)


@pytest.fixture(scope="module")
def placeholder_cleanup_mod():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "cleanup" / "null_placeholder_phones.py"
    name = "null_placeholder_phones_test_mod"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Script mutates sys.path — mirror normal execution
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = S()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _seed_three_placeholder_two_real(db) -> None:
    suf = uuid.uuid4().hex[:8]
    rows = [
        Provider(
            provider_name=f"Placeholder A {suf}",
            category="retail",
            phone="(928) 555-0100",
            verified=True,
            draft=False,
            is_active=True,
            source="test-home-queries",
        ),
        Provider(
            provider_name=f"Placeholder B {suf}",
            category="retail",
            phone="(212) 555-0199",
            verified=True,
            draft=False,
            is_active=True,
            source="test-home-queries",
        ),
        Provider(
            provider_name=f"Placeholder C {suf}",
            category="retail",
            phone="9285550100",
            verified=True,
            draft=False,
            is_active=True,
            source="test-home-queries",
        ),
        Provider(
            provider_name=f"Real A {suf}",
            category="retail",
            phone="(928) 855-1234",
            verified=True,
            draft=False,
            is_active=True,
            source="test-home-queries",
        ),
        Provider(
            provider_name=f"Real B {suf}",
            category="retail",
            phone="(928) 555-1234",
            verified=True,
            draft=False,
            is_active=True,
            source="test-home-queries",
        ),
    ]
    db.add_all(rows)
    db.commit()


def test_cleanup_script_dry_run(placeholder_cleanup_mod, db_session, tmp_path: Path) -> None:
    _seed_three_placeholder_two_real(db_session)
    result = placeholder_cleanup_mod.run_placeholder_cleanup(
        db_session, apply=False, log_dir=tmp_path
    )
    assert result.matched == 3
    assert result.updated == 0
    assert result.log_path.is_file()
    assert db_session.query(Provider).filter(Provider.phone.isnot(None)).count() == 5


def test_cleanup_script_apply_idempotent(
    placeholder_cleanup_mod, db_session, tmp_path: Path
) -> None:
    _seed_three_placeholder_two_real(db_session)
    r1 = placeholder_cleanup_mod.run_placeholder_cleanup(db_session, apply=True, log_dir=tmp_path)
    assert r1.matched == 3
    assert r1.updated == 3

    r2 = placeholder_cleanup_mod.run_placeholder_cleanup(db_session, apply=True, log_dir=tmp_path)
    assert r2.matched == 0
    assert r2.updated == 0

    remaining_with_phone = db_session.query(Provider).filter(Provider.phone.isnot(None)).count()
    assert remaining_with_phone == 2


# ─────────── LEGACY_PROVIDER_CATEGORY_LABELS (live map) ───────────


def test_category_label_map_has_widened_entries() -> None:
    """Lock legacy free-text keys in ``LEGACY_PROVIDER_CATEGORY_LABELS``."""
    from app.home.queries import LEGACY_PROVIDER_CATEGORY_LABELS

    widened = {
        "general_contractor",
        "real_estate",
        "insurance",
        "financial",
        "legal",
        "event_venue",
        "lodging",
        "tourism",
        "education",
        "pet",
        "boat_repair",
        "boat_rental",
    }
    assert widened.issubset(set(LEGACY_PROVIDER_CATEGORY_LABELS.keys()))
