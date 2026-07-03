"""Tests for ``app.chat.disclosure_render`` — Phase 1 keystone, Lane X1.

Spec: ``docs/maintainability/disclosure_renderer_spec.md`` §6.

Coverage:
- Disclosure word golden — every block carries the canonical "Sponsored".
- Tone allowlist — superlatives / marketing voice / comparatives rejected.
- Regime gating — SPECIFIC_QUALITY returns None regardless of inventory.
- GENERIC_CATEGORY happy path — verified factual sponsor renders cleanly.
- EMERGENCY_URGENT — verified_fields_present required, organic pairing required,
  temporal overlap enforced. ``getattr`` default keeps the renderer resilient
  to the parallel Lane S1 schema migration.
- Sponsor pick — deterministic tie-break (weight desc, created_at asc).
- Feature flag — env var off by default; toggling on flips ``is_renderer_enabled``.
- Regression golden — canned query + sponsor inventory matches the JSON fixture.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.chat.disclosure_render import (
    DISALLOWED_PHRASES,
    DISCLOSURE_WORD,
    FEATURE_FLAG_ENV_VAR,
    PlacementRegime,
    RenderDecision,
    SponsoredBlock,
    _check_tone_allowlist,
    _pick_sponsor,
    consume_decision,
    is_renderer_enabled,
    record_decision,
    render_sponsored_block,
    render_with_decision,
    reset_decision_context,
    select_placement_regime,
)
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.models import Sponsor, SponsorStatus

# ─────────── fixtures ───────────


_GOLDEN_PATH = Path(__file__).resolve().parent / "fixtures" / "disclosure_regression_golden.json"


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture(autouse=True)
def _wipe_sponsors(db: Session):
    """Each test starts with no sponsors so prior runs don't bleed in."""
    db.query(Sponsor).delete()
    db.commit()
    yield
    db.query(Sponsor).delete()
    db.commit()


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


def _make_sponsor(
    db: Session,
    *,
    name: str | None = None,
    status: str = SponsorStatus.LIVE.value,
    active: bool = True,
    headline: str | None = None,
    pitch: str | None = None,
    attribution_text: str | None = "local pro",
    cta_label: str = "Visit",
    cta_url: str = "https://example.com",
    weight: int = 0,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    verified_fields_present: bool = False,
) -> Sponsor:
    name = name or f"Sponsor {_suffix()}"
    sp = Sponsor(
        name=name,
        status=status,
        active=active,
        headline=headline,
        pitch=pitch,
        attribution_text=attribution_text,
        cta_label=cta_label,
        cta_url=cta_url,
        weight=weight,
        starts_at=starts_at,
        ends_at=ends_at,
        verified_fields_present=verified_fields_present,
    )
    db.add(sp)
    db.flush()
    return sp


def _intent(
    *,
    mode: str = "ask",
    sub_intent: str = "GENERAL_QUESTION",
    entity: str | None = None,
    inferred_category: str | None = None,
) -> SimpleNamespace:
    """Duck-typed IntentResult — the renderer reads via getattr."""
    return SimpleNamespace(
        mode=mode,
        sub_intent=sub_intent,
        entity=entity,
        inferred_category=inferred_category,
    )


# ─────────── 1. disclosure word golden ───────────


def test_disclosure_word_constant_is_canonical() -> None:
    assert DISCLOSURE_WORD == "Sponsored"


def test_disclosure_word_always_canonical_generic(db: Session) -> None:
    """Every rendered block carries the literal "Sponsored", regime B."""
    sponsor = _make_sponsor(
        db,
        name="Brew Haven",
        attribution_text="local coffee roaster",
        headline="Hand-roasted espresso, open 7 AM to 6 PM.",
    )
    db.commit()
    block = render_sponsored_block(
        regime=PlacementRegime.GENERIC_CATEGORY,
        candidate_sponsors=[sponsor],
        query_context={"organic_rows": [], "category": "coffee"},
        db=db,
    )
    assert block is not None
    assert block.disclosure_word == DISCLOSURE_WORD
    assert block.disclosure_word == "Sponsored"


def test_disclosure_word_always_canonical_emergency(db: Session) -> None:
    """Emergency-urgent block also carries the canonical word."""
    now_wall = datetime(2026, 5, 8, 12, 0)
    now_bind = now_wall.replace(tzinfo=LAKE_HAVASU_TZ)
    sponsor = _make_sponsor(
        db,
        name="Youth Center",
        attribution_text="community programs",
        headline="Free Saturday open gym for ages 5 to 12.",
        verified_fields_present=True,
        starts_at=now_bind - timedelta(days=1),
        ends_at=now_bind + timedelta(days=30),
    )
    db.commit()
    block = render_sponsored_block(
        regime=PlacementRegime.EMERGENCY_URGENT,
        candidate_sponsors=[sponsor],
        query_context={
            "organic_rows": [{"title": "Aquatic Center open swim"}],
            "date_context": now_wall,
        },
        db=db,
    )
    assert block is not None
    assert block.disclosure_word == "Sponsored"


# ─────────── 2. tone allowlist ───────────


def test_tone_allowlist_rejects_superlatives(db: Session) -> None:
    sponsor = _make_sponsor(
        db,
        name="Best Coffee Ever",
        attribution_text="award-winning cafe",
        headline="Best coffee in Lake Havasu!",
    )
    db.commit()
    block = render_sponsored_block(
        regime=PlacementRegime.GENERIC_CATEGORY,
        candidate_sponsors=[sponsor],
        query_context={"organic_rows": [], "category": "coffee"},
        db=db,
    )
    assert block is None


def test_tone_allowlist_rejects_marketing_voice(db: Session) -> None:
    sponsor = _make_sponsor(
        db,
        name="Pristine Roasters",
        attribution_text="amazing coffee experience",
        headline="A perfect cup, every time.",
    )
    db.commit()
    block = render_sponsored_block(
        regime=PlacementRegime.GENERIC_CATEGORY,
        candidate_sponsors=[sponsor],
        query_context={"organic_rows": [], "category": "coffee"},
        db=db,
    )
    assert block is None


def test_tone_allowlist_rejects_comparative(db: Session) -> None:
    sponsor = _make_sponsor(
        db,
        name="Better Coffee Co",
        attribution_text="local roastery",
        headline="Better than the chain shop down the road.",
    )
    db.commit()
    block = render_sponsored_block(
        regime=PlacementRegime.GENERIC_CATEGORY,
        candidate_sponsors=[sponsor],
        query_context={"organic_rows": [], "category": "coffee"},
        db=db,
    )
    assert block is None


def test_tone_allowlist_rejects_false_scarcity(db: Session) -> None:
    sponsor = _make_sponsor(
        db,
        name="Brew Now Co",
        attribution_text="local roastery",
        headline="Limited time offer this week.",
    )
    db.commit()
    block = render_sponsored_block(
        regime=PlacementRegime.GENERIC_CATEGORY,
        candidate_sponsors=[sponsor],
        query_context={"organic_rows": [], "category": "coffee"},
        db=db,
    )
    assert block is None


def test_tone_allowlist_unit_passes_factual() -> None:
    """``_check_tone_allowlist`` accepts plain factual descriptors."""
    assert _check_tone_allowlist(
        "Sponsored",
        body="Open 7 AM to 6 PM weekdays. Sourced from regional roasters.",
        attribution="Brew Haven — local coffee roaster",
    )


def test_tone_allowlist_unit_lists_all_documented_phrases() -> None:
    """Each documented phrase trips the allowlist (regression on coverage)."""
    samples: dict[str, str] = {
        "best": "best in town",
        "award": "an award-winning local pick",
        "highly rated": "highly rated by visitors",
        "perfect": "a perfect spot for brunch",
        "must try": "you must try the special",
        "limited time": "a limited time offer",
        "better than": "better than anywhere else",
        "exclusive": "exclusive to our members",
    }
    # Sanity: each sample really does trip at least one pattern.
    for label, text in samples.items():
        assert not _check_tone_allowlist("Sponsored", body=text, attribution="x"), (
            f"expected '{label}' phrase to trip allowlist; sample={text!r}"
        )
    # And the documented phrase list isn't empty (sanity on the export).
    assert len(DISALLOWED_PHRASES) >= 20


# ─────────── 3. regime gating ───────────


def test_regime_specific_quality_zero_sponsored(db: Session) -> None:
    """Specific-quality + entity → SPECIFIC_QUALITY → renderer returns None."""
    intent = _intent(sub_intent="HOURS_LOOKUP", entity="Barley Brothers")
    regime = select_placement_regime(intent)
    assert regime == PlacementRegime.SPECIFIC_QUALITY

    sponsor = _make_sponsor(db, name="Test")
    db.commit()
    block = render_sponsored_block(
        regime=regime,
        candidate_sponsors=[sponsor],
        query_context={},
        db=db,
    )
    assert block is None


def test_regime_specific_quality_for_all_listed_sub_intents() -> None:
    for sub in (
        "PHONE_LOOKUP",
        "WEBSITE_LOOKUP",
        "HOURS_LOOKUP",
        "LOCATION_LOOKUP",
        "RATING_LOOKUP",
        "REVIEW_COUNT_LOOKUP",
        "TIME_LOOKUP",
        "OPEN_NOW",
    ):
        regime = select_placement_regime(_intent(sub_intent=sub, entity="Some Biz"))
        assert regime == PlacementRegime.SPECIFIC_QUALITY, sub


def test_regime_generic_category_when_no_entity() -> None:
    # LIST_BY_CATEGORY is the REAL classifier sub_intent ("show me barbers"); the
    # other three are retained synthetic labels. All map to GENERIC_CATEGORY when
    # no entity is resolved (2026-07-03 wiring closed the prod gap).
    for sub in ("LIST_BY_CATEGORY", "GENERAL_QUESTION", "RECOMMENDATION", "DISCOVERY"):
        regime = select_placement_regime(_intent(sub_intent=sub, entity=None))
        assert regime == PlacementRegime.GENERIC_CATEGORY, sub


def test_regime_generic_category_falls_back_to_specific_when_entity_present() -> None:
    """Even a category-shaped sub_intent collapses to SPECIFIC_QUALITY when an
    entity is resolved — that's a 'tell me about X' query, not a category browse."""
    regime = select_placement_regime(_intent(sub_intent="LIST_BY_CATEGORY", entity="Hava Cafe"))
    assert regime == PlacementRegime.SPECIFIC_QUALITY


def test_regime_open_ended_stays_specific_quality() -> None:
    """The catch-all OPEN_ENDED is deliberately NOT generic-category — a vague
    'what should I do' must never be monetized (stays zero-sponsored)."""
    regime = select_placement_regime(_intent(sub_intent="OPEN_ENDED", entity=None))
    assert regime == PlacementRegime.SPECIFIC_QUALITY


def test_real_classifier_category_browse_routes_to_generic_category() -> None:
    """End-to-end proof the audit's wiring gap is closed: a real activity-category
    listing the classifier tags LIST_BY_CATEGORY (no entity) selects the
    GENERIC_CATEGORY regime — not just the synthetic test labels."""
    from app.chat.intent_classifier import classify

    result = classify("list of swim classes in havasu")
    assert result.sub_intent == "LIST_BY_CATEGORY"
    assert result.entity in (None, "")
    assert select_placement_regime(result) == PlacementRegime.GENERIC_CATEGORY


def test_regime_emergency_urgent_for_listed_sub_intents() -> None:
    for sub in ("DATE_LOOKUP", "NEXT_OCCURRENCE", "AGE_LOOKUP", "COST_LOOKUP"):
        regime = select_placement_regime(_intent(sub_intent=sub))
        assert regime == PlacementRegime.EMERGENCY_URGENT, sub


def test_regime_non_ask_mode_is_specific_quality() -> None:
    """``contribute`` / ``correct`` / ``chat`` modes are not sponsored-eligible."""
    for mode in ("contribute", "correct", "chat"):
        regime = select_placement_regime(_intent(mode=mode, sub_intent="ANYTHING"))
        assert regime == PlacementRegime.SPECIFIC_QUALITY, mode


# ─────────── 4. generic-category happy path ───────────


def test_generic_category_returns_block_with_factual_sponsor(db: Session) -> None:
    sponsor = _make_sponsor(
        db,
        name="Brew Haven",
        attribution_text="local coffee roaster",
        headline="Hand-roasted espresso, open 7 AM to 6 PM.",
        pitch="Sourced from regional roasters.",
    )
    db.commit()
    block = render_sponsored_block(
        regime=PlacementRegime.GENERIC_CATEGORY,
        candidate_sponsors=[sponsor],
        query_context={"organic_rows": [], "category": "coffee"},
        db=db,
    )
    assert block is not None
    assert isinstance(block, SponsoredBlock)
    assert block.regime == PlacementRegime.GENERIC_CATEGORY
    assert block.sponsor_id == sponsor.id
    assert "Brew Haven" in block.attribution
    assert "local coffee roaster" in block.attribution
    assert "Hand-roasted" in block.body
    assert block.cta == "Visit [https://example.com](https://example.com)"
    # No tone violations smuggled through.
    lower = (block.body + " " + block.attribution).lower()
    for forbidden in ("best", "award", "favorite", "amazing"):
        assert forbidden not in lower


def test_generic_category_suppresses_when_no_factual_body(db: Session) -> None:
    """Sponsor with no headline / pitch → empty body → renderer returns None."""
    sponsor = _make_sponsor(
        db,
        name="Quiet Sponsor",
        attribution_text="local pro",
        headline=None,
        pitch=None,
    )
    db.commit()
    block = render_sponsored_block(
        regime=PlacementRegime.GENERIC_CATEGORY,
        candidate_sponsors=[sponsor],
        query_context={"organic_rows": []},
        db=db,
    )
    assert block is None


def test_generic_category_suppresses_when_status_not_live(db: Session) -> None:
    sponsor = _make_sponsor(
        db,
        name="Reviewed Sponsor",
        status=SponsorStatus.REVIEW.value,
        headline="Open 9 to 5.",
    )
    db.commit()
    block = render_sponsored_block(
        regime=PlacementRegime.GENERIC_CATEGORY,
        candidate_sponsors=[sponsor],
        query_context={"organic_rows": []},
        db=db,
    )
    assert block is None


def test_cta_suppressed_when_url_invalid(db: Session) -> None:
    """Non-http URL → CTA omitted, but block still renders if body OK."""
    sponsor = _make_sponsor(
        db,
        name="Local Spot",
        attribution_text="neighborhood pick",
        headline="Open 9 to 5 weekdays.",
        cta_url="ftp://example.com/visit",
    )
    db.commit()
    block = render_sponsored_block(
        regime=PlacementRegime.GENERIC_CATEGORY,
        candidate_sponsors=[sponsor],
        query_context={"organic_rows": []},
        db=db,
    )
    assert block is not None
    assert block.cta is None


# ─────────── 5. emergency-urgent gates ───────────


def test_emergency_urgent_requires_verified_fields_present(db: Session) -> None:
    """Even with organic pairing + temporal overlap, missing verified flag suppresses."""
    now_wall = datetime(2026, 5, 8, 12, 0)
    now_bind = now_wall.replace(tzinfo=LAKE_HAVASU_TZ)
    sponsor = _make_sponsor(
        db,
        name="Unverified Camp",
        attribution_text="community programs",
        headline="Saturday workshops for kids.",
        verified_fields_present=False,  # explicit
        starts_at=now_bind - timedelta(days=1),
        ends_at=now_bind + timedelta(days=30),
    )
    db.commit()
    block = render_sponsored_block(
        regime=PlacementRegime.EMERGENCY_URGENT,
        candidate_sponsors=[sponsor],
        query_context={
            "organic_rows": [{"title": "Aquatic Center open swim"}],
            "date_context": now_wall,
        },
        db=db,
    )
    assert block is None


def test_emergency_urgent_defensive_when_field_absent_on_object(db: Session) -> None:
    """``getattr(..., 'verified_fields_present', False)`` works on objects without
    the field — guards against running before Lane S1 lands.

    Sanity-checked here against a stand-in object so the test exercises the
    defensive code path even though the migrated model exposes the column."""

    class _LooseSponsor:
        def __init__(self) -> None:
            self.id = "stand-in"
            self.status = SponsorStatus.LIVE.value
            self.name = "Pre-migration Sponsor"
            self.attribution_text = "community programs"
            self.headline = "Saturday workshops for kids."
            self.pitch = None
            self.cta_label = "Visit"
            self.cta_url = "https://example.com"
            self.weight = 0
            self.starts_at = None
            self.ends_at = None
            self.created_at = datetime(2026, 1, 1)

    block = render_sponsored_block(
        regime=PlacementRegime.EMERGENCY_URGENT,
        candidate_sponsors=[_LooseSponsor()],  # type: ignore[list-item]
        query_context={
            "organic_rows": [{"title": "Aquatic Center open swim"}],
            "date_context": datetime(2026, 5, 8, 12, 0),
        },
        db=db,
    )
    # Default False for missing attribute → emergency suppression is correct.
    assert block is None


def test_emergency_urgent_requires_organic_pairing(db: Session) -> None:
    now_wall = datetime(2026, 5, 8, 12, 0)
    now_bind = now_wall.replace(tzinfo=LAKE_HAVASU_TZ)
    sponsor = _make_sponsor(
        db,
        name="Youth Center",
        attribution_text="community programs",
        headline="Free Saturday open gym.",
        verified_fields_present=True,
        starts_at=now_bind - timedelta(days=1),
        ends_at=now_bind + timedelta(days=30),
    )
    db.commit()
    block = render_sponsored_block(
        regime=PlacementRegime.EMERGENCY_URGENT,
        candidate_sponsors=[sponsor],
        query_context={"organic_rows": [], "date_context": now_wall},
        db=db,
    )
    assert block is None


def test_emergency_urgent_temporal_overlap_required(db: Session) -> None:
    now_wall = datetime(2026, 5, 8, 12, 0)
    now_bind = now_wall.replace(tzinfo=LAKE_HAVASU_TZ)
    sponsor = _make_sponsor(
        db,
        name="Old Summer Camp",
        attribution_text="community programs",
        headline="Saturday workshops for kids.",
        verified_fields_present=True,
        starts_at=now_bind - timedelta(days=60),
        ends_at=now_bind - timedelta(days=10),  # ended 10 days ago
    )
    db.commit()
    block = render_sponsored_block(
        regime=PlacementRegime.EMERGENCY_URGENT,
        candidate_sponsors=[sponsor],
        query_context={
            "organic_rows": [{"title": "Aquatic Center open swim"}],
            "date_context": now_wall,
        },
        db=db,
    )
    assert block is None


def test_emergency_urgent_renders_when_all_gates_pass(db: Session) -> None:
    now_wall = datetime(2026, 5, 8, 12, 0)
    now_bind = now_wall.replace(tzinfo=LAKE_HAVASU_TZ)
    sponsor = _make_sponsor(
        db,
        name="Youth Center",
        attribution_text="community programs",
        headline="Free Saturday open gym for ages 5 to 12.",
        verified_fields_present=True,
        starts_at=now_bind - timedelta(days=1),
        ends_at=now_bind + timedelta(days=30),
    )
    db.commit()
    block = render_sponsored_block(
        regime=PlacementRegime.EMERGENCY_URGENT,
        candidate_sponsors=[sponsor],
        query_context={
            "organic_rows": [{"title": "Aquatic Center open swim"}],
            "date_context": now_wall,
        },
        db=db,
    )
    assert block is not None
    assert block.regime == PlacementRegime.EMERGENCY_URGENT
    assert "Youth Center" in block.attribution


# ─────────── 6. sponsor pick determinism ───────────


def test_pick_sponsor_prefers_highest_weight(db: Session) -> None:
    older_low = _make_sponsor(db, name="Low weight", weight=1)
    newer_high = _make_sponsor(db, name="High weight", weight=10)
    db.commit()
    chosen = _pick_sponsor([older_low, newer_high])
    assert chosen is newer_high


def test_pick_sponsor_breaks_ties_by_oldest_created_at(db: Session) -> None:
    """Equal weight → earliest ``created_at`` wins."""
    first = _make_sponsor(db, name="First", weight=5)
    db.commit()
    # Force a later created_at for the second sponsor (server default just
    # uses datetime.now()).
    second = _make_sponsor(db, name="Second", weight=5)
    second.created_at = first.created_at + timedelta(seconds=10)
    db.commit()
    chosen = _pick_sponsor([second, first])  # order shouldn't matter
    assert chosen is first


def test_pick_sponsor_returns_none_for_empty_list() -> None:
    assert _pick_sponsor([]) is None


# ─────────── 7. feature flag ───────────


def test_feature_flag_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(FEATURE_FLAG_ENV_VAR, raising=False)
    assert is_renderer_enabled() is False


def test_feature_flag_true_enables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FEATURE_FLAG_ENV_VAR, "true")
    assert is_renderer_enabled() is True


def test_feature_flag_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FEATURE_FLAG_ENV_VAR, "TRUE")
    assert is_renderer_enabled() is True
    monkeypatch.setenv(FEATURE_FLAG_ENV_VAR, "True")
    assert is_renderer_enabled() is True


def test_feature_flag_other_values_off(monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("false", "0", "yes", "1", "", "  "):
        monkeypatch.setenv(FEATURE_FLAG_ENV_VAR, v)
        assert is_renderer_enabled() is False, v


# ─────────── 8. regression golden file ───────────


# ─────────── 9. P2.OBS.1 — RenderDecision + contextvar telemetry ───────────


def test_render_decision_dataclass_fields() -> None:
    d = RenderDecision(
        regime=PlacementRegime.GENERIC_CATEGORY,
        eligible=True,
        sponsor_id="sid",
        tone_allowlist_passed=True,
    )
    assert d.regime == PlacementRegime.GENERIC_CATEGORY
    assert d.eligible is True
    assert d.sponsor_id == "sid"
    assert d.tone_allowlist_passed is True


def test_consume_decision_is_one_shot() -> None:
    reset_decision_context()
    record_decision(
        RenderDecision(
            regime=PlacementRegime.GENERIC_CATEGORY,
            eligible=False,
            sponsor_id=None,
            tone_allowlist_passed=None,
        )
    )
    c1 = consume_decision()
    assert c1 is not None
    assert c1.eligible is False
    assert consume_decision() is None


def test_reset_decision_context_clears_without_consume() -> None:
    reset_decision_context()
    record_decision(
        RenderDecision(
            regime=PlacementRegime.EMERGENCY_URGENT,
            eligible=True,
            sponsor_id="x",
            tone_allowlist_passed=True,
        )
    )
    reset_decision_context()
    assert consume_decision() is None


def test_render_with_decision_records_success(db: Session) -> None:
    reset_decision_context()
    sponsor = _make_sponsor(
        db,
        name="Brew Haven",
        attribution_text="local coffee roaster",
        headline="Hand-roasted espresso, open 7 AM to 6 PM.",
    )
    db.commit()
    block = render_with_decision(
        regime=PlacementRegime.GENERIC_CATEGORY,
        candidate_sponsors=[sponsor],
        query_context={"organic_rows": [], "category": "coffee"},
        db=db,
    )
    assert block is not None
    snap = consume_decision()
    assert snap is not None
    assert snap.regime == PlacementRegime.GENERIC_CATEGORY
    assert snap.eligible is True
    assert snap.sponsor_id == sponsor.id
    assert snap.tone_allowlist_passed is True


def test_render_with_decision_records_tone_failure(db: Session) -> None:
    reset_decision_context()
    sponsor = _make_sponsor(
        db,
        name="Best Coffee Ever",
        attribution_text="award-winning cafe",
        headline="Best coffee in Lake Havasu!",
    )
    db.commit()
    assert (
        render_with_decision(
            regime=PlacementRegime.GENERIC_CATEGORY,
            candidate_sponsors=[sponsor],
            query_context={"organic_rows": [], "category": "coffee"},
            db=db,
        )
        is None
    )
    snap = consume_decision()
    assert snap is not None
    assert snap.tone_allowlist_passed is False
    assert snap.eligible is True
    assert snap.sponsor_id == sponsor.id


def test_regression_golden_generic_category_coffee(db: Session) -> None:
    """Canned query + sponsor inventory → expected SponsoredBlock shape.

    The fixture is ``tests/fixtures/disclosure_regression_golden.json``.
    """
    golden = json.loads(_GOLDEN_PATH.read_text())

    sp_data = golden["sponsor"]
    sponsor = _make_sponsor(
        db,
        name=sp_data["name"],
        status=sp_data["status"],
        active=sp_data["active"],
        weight=sp_data.get("weight", 0),
        attribution_text=sp_data.get("attribution_text"),
        headline=sp_data.get("headline"),
        pitch=sp_data.get("pitch"),
        cta_label=sp_data.get("cta_label", "Visit"),
        cta_url=sp_data.get("cta_url", "https://example.com"),
    )
    db.commit()

    intent = _intent(
        sub_intent="GENERAL_QUESTION",
        entity=None,
        inferred_category=golden.get("expected_regime"),
    )
    regime = select_placement_regime(intent)
    assert regime.value == golden["expected_regime"]

    block = render_sponsored_block(
        regime=regime,
        candidate_sponsors=[sponsor],
        query_context={
            "organic_rows": golden["organic_rows"],
            "category": "coffee",
        },
        db=db,
    )

    assert block is not None
    assert block.disclosure_word == golden["expected_disclosure_word"]
    for s in golden["expected_attribution_contains"]:
        assert s in block.attribution, (s, block.attribution)
    for s in golden["expected_body_contains"]:
        assert s in block.body, (s, block.body)
    body_lower = block.body.lower()
    for s in golden["expected_body_excludes"]:
        assert s.lower() not in body_lower, (s, block.body)
    assert block.cta == golden["expected_cta"]
    assert block.sponsor_id == sponsor.id
    assert block.regime == PlacementRegime.GENERIC_CATEGORY
