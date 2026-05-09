"""Tests for ``app.chat.intent_classifier`` URGENT_NOW sub_intent (Backlog #43).

Verifies that urgent-phrasing queries ("right now", "urgent", "ASAP",
"emergency", "immediately", "right away", "right this [minute]") classify
as URGENT_NOW, and that ``select_placement_regime`` maps URGENT_NOW to
``PlacementRegime.EMERGENCY_URGENT`` — fixing the spec deviation where
``"plumber, water leak right now"`` routed to ``SPECIFIC_QUALITY``
(safe-default that suppresses sponsored on what should be a high-stakes
urgent query).

Dispatch ordering: URGENT_NOW slots after the specific Tier-1 sub_intents
(AGE_LOOKUP, COST_LOOKUP, etc.) and before OPEN_ENDED. Specific
sub_intents still win when both shapes match — see
``test_specific_sub_intent_wins_over_urgent_now``.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.chat.disclosure_render import PlacementRegime, select_placement_regime
from app.chat.intent_classifier import classify


def test_classifier_recognizes_right_now() -> None:
    result = classify("plumber right now")
    assert result.mode == "ask"
    assert result.sub_intent == "URGENT_NOW"


def test_classifier_recognizes_urgent() -> None:
    result = classify("I need an urgent locksmith")
    assert result.mode == "ask"
    assert result.sub_intent == "URGENT_NOW"


def test_classifier_recognizes_asap() -> None:
    result = classify("boat repair ASAP")
    assert result.mode == "ask"
    assert result.sub_intent == "URGENT_NOW"


def test_classifier_recognizes_emergency() -> None:
    result = classify("emergency dental")
    assert result.mode == "ask"
    assert result.sub_intent == "URGENT_NOW"


def test_specific_sub_intent_wins_over_urgent_now() -> None:
    """AGE_LOOKUP (in INTENT_PATTERNS) matches first and short-circuits before
    the URGENT_NOW check that follows the for-loop. Order of dispatch matters."""
    result = classify("kids activities right now for ages 5 to 12")
    assert result.mode == "ask"
    assert result.sub_intent == "AGE_LOOKUP"


def test_no_urgent_phrasing_classifies_open_ended() -> None:
    """URGENT_NOW does NOT eat plain-vanilla queries — only triggers on the
    specific urgent-phrasing markers."""
    result = classify("find a plumber")
    assert result.mode == "ask"
    assert result.sub_intent == "OPEN_ENDED"


def test_select_placement_regime_maps_urgent_now_to_emergency() -> None:
    intent = SimpleNamespace(
        mode="ask",
        sub_intent="URGENT_NOW",
        entity=None,
    )
    assert select_placement_regime(intent) == PlacementRegime.EMERGENCY_URGENT


def test_e2e_water_leak_query_classifies_urgent_then_emergency_regime() -> None:
    """End-to-end: classifier returns URGENT_NOW → renderer regime is
    EMERGENCY_URGENT.

    This is the canonical spec example from Lane X2.1's diagnostic and
    Backlog #43 — previously routed to SPECIFIC_QUALITY (sponsored
    suppressed on a high-stakes urgent query)."""
    result = classify("plumber, water leak right now")
    assert result.sub_intent == "URGENT_NOW"
    regime = select_placement_regime(result)
    assert regime == PlacementRegime.EMERGENCY_URGENT
