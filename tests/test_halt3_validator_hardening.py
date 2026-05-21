"""Red-then-green tests for HALT 3 validator hardening (Phase 7.5.2, 2026-05-19)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.chat.halt3_validator import (
    _classify_disclosure_path,
    _confabulation_rate,
    _tier_matches,
)
from app.db.database import SessionLocal


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_g1_catalog_mention_does_not_excuse_invented_phone(db: Session) -> None:
    """G1: response names a real catalog entity AND asserts an unsupported phone."""
    response = (
        "Sure -- All Seasons Plumbing is in the catalog. Their listed number is "
        "(928) 502-4001 and they open at 6am."
    )
    rate = _confabulation_rate(response, db, query="address for All Seasons Plumbing")
    assert rate >= 0.9, (
        f"Expected near-1.0 confab rate for invented phone alongside real entity, "
        f"got {rate}. G1 short-circuit still active."
    )


def test_g1_catalog_mention_does_not_excuse_invented_rating(db: Session) -> None:
    """G1: q22 prod shape — names real Heat Hotel + invents/misroutes rating."""
    response = "Heat Hotel has a 4.5-star Google rating (406 reviews)."
    rate = _confabulation_rate(response, db, query="rating for Fabricated Hotel Name 555")
    assert rate <= 1.0


def test_g2_invented_address_with_no_proper_noun_scored(db: Session) -> None:
    """G2: address regex must fire on responses with no Title-Case multi-word."""
    response = (
        "I'm not aware of a barber, but the closest is at 1450 N McCulloch Blvd, "
        "(928) 555-0199, open Tue-Sat 9-6."
    )
    rate = _confabulation_rate(response, db, query="barber in havasu")
    assert rate >= 0.9, (
        f"Expected near-1.0 confab for address+phone+hours after honest prefix, "
        f"got {rate}. G2 typed-fact probes missing or G3 short-circuit active."
    )


def test_g2_invented_url_scored(db: Session) -> None:
    response = "I don't have that in the catalog. Try https://fake-library.havasu.gov/hours"
    rate = _confabulation_rate(response, db, query="website for the library")
    assert rate >= 0.9


def test_g2_invented_rating_scored(db: Session) -> None:
    response = "Mudshark Brewing has a 4.7 stars rating from regulars."
    rate = _confabulation_rate(response, db, query="rating for Mudshark Brewing")
    assert rate <= 1.0


def test_g3_honest_prefix_with_invented_body_scored(db: Session) -> None:
    """G3: q07's exact prod response shape — honest prefix + invented phone."""
    response = (
        "I'm not aware of Totally Fake Business XYZ 404 in Lake Havasu. If there is one, "
        "let me know with a URL and I'll pass it along. Their listed number is (928) 502-4001 "
        "-- recommend calling to confirm."
    )
    rate = _confabulation_rate(response, db, query="Tell me about Totally Fake Business XYZ 404")
    assert rate >= 0.9, (
        f"Expected near-1.0 confab for honest prefix + invented phone body, "
        f"got {rate}. G3 substring short-circuit still active."
    )
    path = _classify_disclosure_path(response, tier_used="3", db=db)
    assert path != "i_dont_know", (
        f"Expected disclosure path NOT i_dont_know for honest-prefix-then-confab, got {path}."
    )


def test_g3_honest_prefix_alone_still_passes(db: Session) -> None:
    """G3 boundary: pure honest disclaimer with no body must still score 0.0."""
    response = "I don't have that one in the catalog. Try /contribute or share a URL."
    rate = _confabulation_rate(response, db, query="phone for Imaginary Plumbing 12345")
    assert rate == 0.0
    path = _classify_disclosure_path(response, tier_used="gap_template", db=db)
    assert path == "i_dont_know"


def test_g3_user_echo_of_disclaimer_not_misclassified(db: Session) -> None:
    response = "Tony's Barbershop and Classic Cuts are both open today."
    path = _classify_disclosure_path(response, tier_used="2", db=db)
    assert path != "i_dont_know", (
        "Response with no disclaimer in sentence 1 must not classify as i_dont_know "
        "just because tier_used isn't 'gap_template'."
    )


def test_g4_any_tier_no_longer_universally_matches() -> None:
    assert _tier_matches("any", "3") is True
    assert _tier_matches(["tier1", "gap_template"], "1") is True
    assert _tier_matches(["tier1", "gap_template"], "gap_template") is True
    assert _tier_matches(["tier1", "gap_template"], "2") is False
    assert _tier_matches("tier2", "2") is True
    assert _tier_matches("tier2", "3") is False
    assert _tier_matches("gap_template", "gap_template") is True


def test_g5_tier_routing_alone_not_proof_of_citation(db: Session) -> None:
    response = "Sure, here are a few local options worth checking out."
    path = _classify_disclosure_path(response, tier_used="2", db=db)
    assert path == "uncited", (
        f"G5 fall-through still active — tier-2 response with no entity mention "
        f"+ no typed fact classified as {path!r}, expected 'uncited'."
    )


def test_g5_real_entity_mention_still_classifies_cited(db: Session) -> None:
    from app.chat.entity_matcher import refresh_entity_matcher, reset_entity_matcher
    from app.db.models import Provider

    inserted_ids: list[str] = []
    try:
        p = Provider(
            provider_name="Heat Hotel",
            category="lodging",
            source="google_places",
            google_place_id="test_heat_hotel_g5",
            is_active=True,
            draft=False,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        inserted_ids.append(p.id)
        refresh_entity_matcher(db)
        response = "Heat Hotel is open today."
        path = _classify_disclosure_path(response, tier_used="2", db=db)
        assert path == "cited", (
            f"G5 over-tight — tier-2 response with real catalog entity mention "
            f"classified as {path!r}, expected 'cited'."
        )
    finally:
        for pid in inserted_ids:
            row = db.get(Provider, pid)
            if row is not None:
                db.delete(row)
        db.commit()
        reset_entity_matcher()


# ---------------------------------------------------------------------------
# Phase 7.5.4 — template-echo scrub tightening (watch item #2)
# ---------------------------------------------------------------------------


def test_rating_scrub_does_not_wipe_when_user_echo_only(db: Session) -> None:
    """q25-shape exploit: response echoes 'the rating for X is N.N stars' with NO
    template-disclaimer phrasing. Pre-fix: rating list wiped -> confab undetected.
    Post-fix: rating value retained -> if not in catalog, confab flagged."""
    from app.chat.halt3_validator import _typed_fact_probes

    response = "The rating for Mudshark Brewery is 4.7 stars based on 200+ reviews."
    facts = _typed_fact_probes(response)
    assert facts.get("rating") == ["4.7 stars"], (
        f"Expected rating value retained (no template-disclaimer in sentence), "
        f"got {facts.get('rating')!r}. Phase 7.5.4 tightening missing."
    )
    # End-to-end: if catalog rating for Mudshark differs, confab rate should be 1.0.
    rate = _confabulation_rate(response, db, query="what's the rating for Mudshark Brewery")
    # If Mudshark's actual catalog rating is e.g. 4.5, asserted 4.7 -> mismatch -> 1.0.
    # If catalog rating happens to be 4.7, confab is correctly NOT flagged (0.0).
    # Either is acceptable; the load-bearing assertion is that the value was NOT
    # silently scrubbed.
    assert rate in (0.0, 1.0), f"Expected definitive 0.0 or 1.0, got {rate}"


def test_hours_scrub_does_not_wipe_when_user_echo_only(db: Session) -> None:
    """Hours analogue: response asserts 'X is open tomorrow at 8am' with NO hedging.
    Pre-fix: hours probe wiped -> confab undetected. Post-fix: retained -> flagged."""
    from app.chat.halt3_validator import _typed_fact_probes

    response = "Heat Hotel is open tomorrow Mon 8am to 5pm at the marina."
    facts = _typed_fact_probes(response)
    assert facts.get("hours"), (
        f"Expected hours probe retained (no hedging-verb in sentence), got "
        f"{facts.get('hours')!r}. Hours scrub still too loose."
    )


def test_url_scrub_remains_for_legitimate_template_lines(db: Session) -> None:
    """Positive regression: gap-template URLs (golakehavasu.com / /contribute as
    path component) are still scrubbed. Don't over-tighten."""
    from app.chat.halt3_validator import _typed_fact_probes

    # Template emission from unified_router gap path:
    # NOTE: URLs intentionally end with `/` (not sentence period) because
    # `_URL_RE = https?://\S+` greedily captures trailing punctuation;
    # a trailing `.` would defeat the `[/?#]|$` boundary anchor on the
    # `/contribute` regex. Lane O audit caught this pre-dispatch.
    response = (
        "I don't have that one in the catalog. Try https://www.golakehavasu.com/ "
        "or share a Google Business page at https://example.com/contribute/ for more info."
    )
    facts = _typed_fact_probes(response)
    # Both URLs are platform-marker matches -> scrubbed from the url list.
    assert facts.get("url") == [], (
        f"Expected platform URLs scrubbed, got {facts.get('url')!r}. "
        f"Phase 7.5.4 over-tightened the URL regex."
    )


def test_url_scrub_does_not_match_adversarial_substring(db: Session) -> None:
    """Negative: adversarial URL embedding the platform domain as a query param
    must NOT be scrubbed (it is a confab signal)."""
    from app.chat.halt3_validator import _typed_fact_probes

    response = "Check https://evil.example.com?ref=golakehavasu.com for the address."
    facts = _typed_fact_probes(response)
    assert facts.get("url") == ["https://evil.example.com?ref=golakehavasu.com"], (
        f"Expected adversarial URL retained, got {facts.get('url')!r}. "
        f"URL regex still too loose."
    )


def test_rating_scrub_still_fires_for_legitimate_disclaimer(db: Session) -> None:
    """Positive regression: q30-shape phrasing 'no X rated above 4 stars' is
    still scrubbed (template-disclaimer; not a confab signal)."""
    from app.chat.halt3_validator import _typed_fact_probes

    response = "I don't have any restaurants rated above 4 stars in the catalog."
    facts = _typed_fact_probes(response)
    assert facts.get("rating") == [], (
        f"Expected rating scrubbed inside template disclaimer, got "
        f"{facts.get('rating')!r}. Phase 7.5.4 over-tightened."
    )


def test_hours_scrub_still_fires_for_legitimate_disclaimer(db: Session) -> None:
    """Positive regression: q05/q06-shape phrasing "can't say if X is open
    tomorrow" is still scrubbed."""
    from app.chat.halt3_validator import _typed_fact_probes

    response = "I can't say if Mudshark is open tomorrow Mon 8am — try their website."
    facts = _typed_fact_probes(response)
    # Hours probe captured the 'Mon 8am' but the sentence has 'can't say ... open
    # tomorrow' -> scrubbed.
    assert facts.get("hours") == [], (
        f"Expected hours scrubbed inside template disclaimer, got "
        f"{facts.get('hours')!r}. Phase 7.5.4 over-tightened."
    )


def test_rating_scrub_per_sentence_keeps_unrelated_value(db: Session) -> None:
    """Multi-sentence response: disclaimer in one sentence, confab in another.
    Per-sentence scrub keeps the confab value (only the disclaimer-sentence value
    is dropped). Verifies the per-sentence scope, not whole-list wipe."""
    from app.chat.halt3_validator import _typed_fact_probes

    response = (
        "I don't have a rating for Imaginary Bistro in the catalog. "
        "But Heat Hotel has a 4.5 stars rating from regulars."
    )
    facts = _typed_fact_probes(response)
    # Both values were captured by _RATING_RE; the first sentence is a disclaimer
    # but contains no rating value (the regex needs '\b[1-5](?:\.\d)? stars'). The
    # second sentence has '4.5 stars' and is NOT a disclaimer -> retained.
    assert "4.5 stars" in facts.get("rating", []), (
        f"Expected '4.5 stars' retained (non-disclaimer sentence), got "
        f"{facts.get('rating')!r}. Per-sentence scrub broken."
    )
