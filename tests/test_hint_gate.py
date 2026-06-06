"""P1-2: the hint-extractor signal gate must not fire the per-turn LLM call on a
bare digit (the prompt can't infer age from a number alone)."""

from __future__ import annotations

from app.chat.hint_extractor import has_hint_signal


def test_bare_digit_does_not_trigger_gate() -> None:
    assert has_hint_signal("is the bar open at 5?") is False
    assert has_hint_signal("table for 4 tonight") is False
    assert has_hint_signal("call them at 928 555 0100") is False


def test_real_age_phrasings_trigger() -> None:
    for q in (
        "activities for my 6-year-old",
        "something for my 8 year old son",
        "classes for a teenager",
        "swim for a 3 month old",
        "programs for 9-12 year olds",
    ):
        assert has_hint_signal(q) is True, q


def test_location_signals_unchanged() -> None:
    assert has_hint_signal("we are staying near the channel") is True
