"""Tests for scripts/category_patrol.py.

Covers ruleset loading, prompt building, verdict parsing, the pure flag/no-flag
decision logic, and the DB write contract -- a dry run touches nothing while
--apply writes the two additive flag columns. The classifier is always injected,
so nothing here hits the network.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete

from app.categories.subcategories import PRIMARY_CATEGORY_SLUGS
from app.db.database import SessionLocal
from app.db.models import Provider
from scripts import category_patrol as cp


def _sig(current_primary: str | None, *, pid: str | None = None, name: str = "Acme") -> cp.ProviderSignals:
    return cp.ProviderSignals(
        id=pid or uuid.uuid4().hex,
        name=name,
        current_primary=current_primary,
        google_primary_category="business",
        google_categories=["thing"],
    )


# ---------------------------------------------------------------------------
# Rulesets
# ---------------------------------------------------------------------------


def test_load_rulesets_real_dir_has_exemplars() -> None:
    rs = cp.load_rulesets()
    assert "professional-services" in rs
    assert "health-wellness-care" in rs
    # README and any non-slug file must be ignored.
    assert "README" not in rs
    assert all(slug in PRIMARY_CATEGORY_SLUGS for slug in rs)


def test_every_primary_has_a_ruleset() -> None:
    """Totality guard: a new primary category can't ship without guidance."""
    rs = cp.load_rulesets()
    missing = set(PRIMARY_CATEGORY_SLUGS) - set(rs)
    assert not missing, f"primaries with no ruleset: {sorted(missing)}"


def test_load_rulesets_ignores_non_slug_files(tmp_path) -> None:
    (tmp_path / "professional-services.md").write_text("pro rules", encoding="utf-8")
    (tmp_path / "not-a-category.md").write_text("junk", encoding="utf-8")
    (tmp_path / "README.md").write_text("readme", encoding="utf-8")
    rs = cp.load_rulesets(tmp_path)
    assert rs == {"professional-services": "pro rules"}


def test_load_rulesets_missing_dir(tmp_path) -> None:
    assert cp.load_rulesets(tmp_path / "nope") == {}


def test_build_messages_embeds_slugs_signals_and_rules() -> None:
    msgs = cp.build_messages(_sig("eat-drink", name="Joe's Diner"), {"eat-drink": "RULE-TEXT"})
    system, user = msgs[0]["content"], msgs[1]["content"]
    assert "eat-drink" in system
    assert "RULE-TEXT" in system
    assert "Joe's Diner" in user


# ---------------------------------------------------------------------------
# parse_verdict
# ---------------------------------------------------------------------------


def test_parse_verdict_valid() -> None:
    v = cp.parse_verdict('{"correct_primary": "pets", "confidence": 0.9, "reason": "vet"}')
    assert v.primary == "pets"
    assert v.confidence == pytest.approx(0.9)
    assert v.reason == "vet"


def test_parse_verdict_invalid_slug_becomes_none() -> None:
    v = cp.parse_verdict('{"correct_primary": "made-up", "confidence": 0.9}')
    assert v.primary is None


def test_parse_verdict_confidence_clamped_and_bad_json_is_null() -> None:
    assert cp.parse_verdict('{"correct_primary": "pets", "confidence": 5}').confidence == 1.0
    assert cp.parse_verdict('{"correct_primary": "pets", "confidence": -2}').confidence == 0.0
    null = cp.parse_verdict("not json")
    assert null.primary is None and null.confidence == 0.0


def test_parse_verdict_none_string_primary() -> None:
    assert cp.parse_verdict('{"correct_primary": "none", "confidence": 0.4}').primary is None


# ---------------------------------------------------------------------------
# evaluate (pure)
# ---------------------------------------------------------------------------


def test_evaluate_flags_confident_disagreement() -> None:
    d = cp.evaluate(_sig("eat-drink"), cp.Verdict("pets", 0.9), threshold=0.75)
    assert d.flag is True


def test_evaluate_no_flag_on_agreement() -> None:
    d = cp.evaluate(_sig("pets"), cp.Verdict("pets", 0.99), threshold=0.75)
    assert d.flag is False


def test_evaluate_no_flag_below_threshold() -> None:
    d = cp.evaluate(_sig("eat-drink"), cp.Verdict("pets", 0.6), threshold=0.75)
    assert d.flag is False


def test_evaluate_no_flag_when_verdict_uncertain() -> None:
    d = cp.evaluate(_sig("eat-drink"), cp.Verdict(None, 0.99), threshold=0.75)
    assert d.flag is False


def test_evaluate_threshold_is_inclusive() -> None:
    d = cp.evaluate(_sig("eat-drink"), cp.Verdict("pets", 0.75), threshold=0.75)
    assert d.flag is True


# ---------------------------------------------------------------------------
# patrol orchestration
# ---------------------------------------------------------------------------


def test_patrol_counts_scanned_and_flagged() -> None:
    sigs = [_sig("eat-drink"), _sig("pets"), _sig("eat-drink")]

    def classifier(s: cp.ProviderSignals) -> cp.Verdict:
        # Anything currently eat-drink is "really" pets, confidently.
        if s.current_primary == "eat-drink":
            return cp.Verdict("pets", 0.95)
        return cp.Verdict(s.current_primary, 0.95)  # agrees -> no flag

    run = cp.patrol(sigs, classifier, threshold=0.75)
    assert run.scanned == 3
    assert len(run.flagged) == 2


# ---------------------------------------------------------------------------
# DB write contract
# ---------------------------------------------------------------------------


def _make_provider(db, *, source: str, primary: str) -> Provider:
    p = Provider(
        provider_name=f"Probe {uuid.uuid4().hex[:6]}",
        category="legacy",
        primary_category=primary,
        source=source,
    )
    db.add(p)
    db.flush()
    return p


def test_load_signals_only_returns_categorized(tmp_source: str) -> None:
    with SessionLocal() as db:
        _make_provider(db, source=tmp_source, primary="eat-drink")
        # A NULL-primary provider must be excluded (that's the export script's job).
        db.add(Provider(provider_name="Uncat", category="legacy", source=tmp_source))
        db.commit()
    with SessionLocal() as db:
        sigs = cp.load_signals(db)
        mine = [s for s in sigs if s.name.startswith("Probe")]
        assert mine and all(s.current_primary is not None for s in mine)


def test_apply_flags_writes_columns(tmp_source: str) -> None:
    with SessionLocal() as db:
        p = _make_provider(db, source=tmp_source, primary="eat-drink")
        pid = p.id
        db.commit()
    decision = cp.evaluate(_sig("eat-drink", pid=pid), cp.Verdict("pets", 0.91), threshold=0.75)
    now = datetime.now(UTC)
    with SessionLocal() as db:
        written = cp.apply_flags(db, [decision], now=now)
        assert written == 1
    with SessionLocal() as db:
        got = db.get(Provider, pid)
        assert got.category_confidence == pytest.approx(0.91)
        assert got.category_flagged_at is not None


def test_dry_run_writes_nothing(tmp_source: str) -> None:
    """patrol() computes flags but never touches the DB; only apply_flags does."""
    with SessionLocal() as db:
        p = _make_provider(db, source=tmp_source, primary="eat-drink")
        pid = p.id
        db.commit()
    sigs = [_sig("eat-drink", pid=pid)]
    run = cp.patrol(sigs, lambda s: cp.Verdict("pets", 0.95), threshold=0.75)
    assert len(run.flagged) == 1
    # No apply_flags call -> columns stay NULL.
    with SessionLocal() as db:
        got = db.get(Provider, pid)
        assert got.category_confidence is None
        assert got.category_flagged_at is None


@pytest.fixture
def tmp_source() -> str:
    source = f"test-patrol-{uuid.uuid4().hex[:8]}"
    yield source
    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.source == source))
        db.commit()
