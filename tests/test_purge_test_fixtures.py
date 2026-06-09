"""Tests for scripts/purge_test_fixtures.py (seed/fixture soft-delete)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from app.db.database import SessionLocal
from app.db.models import Entity, Provider

# Load the script module by path (scripts/ is not an importable package).
# Register it in sys.modules before exec so the frozen-annotation dataclass can
# resolve its own module (dataclasses looks up cls.__module__ in sys.modules).
_SPEC = importlib.util.spec_from_file_location(
    "purge_test_fixtures",
    Path(__file__).resolve().parents[1] / "scripts" / "purge_test_fixtures.py",
)
assert _SPEC and _SPEC.loader
purge = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = purge
_SPEC.loader.exec_module(purge)


# --- match_reason unit coverage ---------------------------------------------


def test_match_reason_flags_named_fixtures() -> None:
    assert purge.match_reason("Acme Plumbing") == "acme plumbing"
    assert purge.match_reason("Crestline Plumbing Test Fixture") == "test fixture"
    assert purge.match_reason("Acme Operator Verified Plumbing") == "acme operator"
    assert purge.match_reason("AskAlpha Services") == "askalpha"
    assert purge.match_reason("AskBeta Services") == "askbeta"
    assert purge.match_reason("123 Bookkeeping") == "numeric bookkeeping/holler"
    assert purge.match_reason("5 Dollar Holler") == "numeric bookkeeping/holler"
    # hash-suffixed dupe
    assert purge.match_reason("Acme Plumbing 1400bbd7") == "acme plumbing"
    assert purge.match_reason("Food c3b782b0") == "hex8 token"


def test_match_reason_leaves_real_names_alone() -> None:
    assert purge.match_reason("Havasu Riverside Bakery") is None
    assert purge.match_reason("Channel 12 News") is None
    assert purge.match_reason("") is None
    assert purge.match_reason(None) is None
    # A 12-char hex token is NOT an 8-char fixture suffix.
    assert purge.match_reason("Order abcdef123456") is None


# --- end-to-end dry-run / apply against the test DB -------------------------


def test_purge_dry_run_then_apply() -> None:
    with SessionLocal() as db:
        fixture_a = Entity(
            entity_type="commercial",
            slug="acme-plumbing-purgetest",
            name="Acme Plumbing PURGETEST",
        )
        fixture_b = Provider(
            provider_name="AskAlpha Services PURGETEST",
            category="home-services",
        )
        already_inactive = Entity(
            entity_type="commercial",
            slug="askbeta-purgetest",
            name="AskBeta Services PURGETEST",
            is_active=False,
        )
        clean = Entity(
            entity_type="commercial",
            slug="havasu-riverside-bakery-purgetest",
            name="Havasu Riverside Bakery",
        )
        event_with_hash = Entity(
            entity_type="event",
            slug="backfill-event-purgetest-1d1559d7",
            name="Backfill Event 1d1559d7",
        )
        db.add_all([fixture_a, fixture_b, already_inactive, clean, event_with_hash])
        db.commit()
        ids = {
            "a": fixture_a.id,
            "b": fixture_b.id,
            "inactive": already_inactive.id,
            "clean": clean.id,
            "event": event_with_hash.id,
        }

    # --- dry run: reports matches, writes nothing ---
    with SessionLocal() as db:
        matches = purge.find_matches(db)
        mine = {(m.table, m.row_id): m for m in matches}
        assert ("entities", ids["a"]) in mine
        assert ("providers", ids["b"]) in mine
        assert ("entities", ids["inactive"]) in mine  # matched but already inactive
        assert ("entities", ids["clean"]) not in mine  # real name, untouched
        assert ("entities", ids["event"]) not in mine  # event scope excluded

        counts = purge.run(apply=False, session=db)
        assert counts["matched"] >= 3

    # nothing was written by the dry run
    with SessionLocal() as db:
        assert db.get(Entity, ids["a"]).is_active is True
        assert db.get(Provider, ids["b"]).is_active is True
        assert db.get(Entity, ids["clean"]).is_active is True

    # --- apply without confirm: refuses, writes nothing ---
    with SessionLocal() as db:
        counts = purge.run(apply=True, confirm=False, session=db)
        assert "soft_deleted" not in counts
        assert db.get(Entity, ids["a"]).is_active is True  # still active

    # --- apply with confirm: soft-delete the active matches only ---
    with SessionLocal() as db:
        counts = purge.run(apply=True, confirm=True, session=db)
        assert counts["soft_deleted"] >= 2

    with SessionLocal() as db:
        assert db.get(Entity, ids["a"]).is_active is False  # soft-deleted
        assert db.get(Provider, ids["b"]).is_active is False  # soft-deleted
        assert db.get(Entity, ids["inactive"]).is_active is False  # stayed inactive
        assert db.get(Entity, ids["clean"]).is_active is True  # real row preserved
        assert db.get(Entity, ids["event"]).is_active is True  # event preserved
