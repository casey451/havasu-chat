"""Unit tests for app.chat.tier3_postprocess._is_sentence_useful (F7) and the
grounding-scaffold leak scrub (P2-1, QA diagnostic 2026-06-12)."""

from __future__ import annotations

import pytest

from app.chat.tier3_postprocess import (
    _SCAFFOLDING_FALLBACK,
    _UNGROUNDED_CONTACT_FALLBACK,
    _is_sentence_useful,
    redact_ungrounded_contact,
    strip_soft_suggest,
)


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("Visit Heat Hotel at 1101 McCulloch Blvd.", True),
        ("Call (928) 555-1234 for reservations.", True),
        ("Check https://example.com for details.", True),
        ("Mudshark Brewery serves IPAs.", True),
        ("Try visiting on a Tuesday.", False),
        ("Visit the Hotel.", False),
        ("See /contribute to add this venue.", True),
    ],
)
def test_is_sentence_useful(sentence: str, expected: bool) -> None:
    assert _is_sentence_useful(sentence) is expected


@pytest.mark.parametrize(
    "leak",
    [
        "The provided rows do not include information on where to get a fishing license.",
        "Based on the provided rows, I can't find that.",
        "The rows provided don't list hours.",
        "I don't have access to the data for that venue.",
        "The data provided does not include a website.",
    ],
)
def test_full_scaffold_leak_becomes_clean_gap(leak: str) -> None:
    out = strip_soft_suggest(leak)
    assert out == _SCAFFOLDING_FALLBACK
    assert "rows" not in out
    assert "provided rows" not in out


def test_scaffold_leak_sentence_dropped_useful_kept() -> None:
    text = (
        "The provided rows do not include a website. "
        "Visit Heat Hotel at 1101 McCulloch Blvd."
    )
    out = strip_soft_suggest(text)
    assert "Heat Hotel" in out
    assert "provided rows" not in out


def test_legit_rows_word_not_scrubbed() -> None:
    # "rows of vines" is not a scaffold reference — must survive untouched.
    text = "There are a few rows of vines at the winery. Call (928) 855-1223 to visit."
    out = strip_soft_suggest(text)
    assert out != _SCAFFOLDING_FALLBACK
    assert "vines" in out


# ---------------------------------------------------------------------------
# F1 — ungrounded contact-info guard
# ---------------------------------------------------------------------------

_CTX = (
    "Context — Lake Havasu catalog snapshot:\n"
    "Provider: Sloane's Craft Kitchen\n"
    "  address: 100 Swanson Ave\n"
    "  phone: (928) 855-1223\n"
)


def test_ungrounded_phone_sentence_dropped() -> None:
    # The audit's failure shape: a fabricated number for a business not in Context.
    text = "Go with Mudshark. Their listed number is (775) 848-5418."
    out = redact_ungrounded_contact(text, _CTX)
    assert "(775) 848-5418" not in out
    assert "775" not in out
    assert "Go with Mudshark." in out


def test_grounded_phone_kept_even_reformatted() -> None:
    # Same number as Context, reformatted by the model — digits match, so kept.
    text = "Call Sloane's at 928-855-1223 to book."
    out = redact_ungrounded_contact(text, _CTX)
    assert out == text


def test_grounded_address_kept() -> None:
    text = "Sloane's is at 100 Swanson Ave."
    out = redact_ungrounded_contact(text, _CTX)
    assert out == text


def test_ungrounded_address_dropped() -> None:
    text = "Head to The Spot. It's at 1101 McCulloch Blvd."
    out = redact_ungrounded_contact(text, _CTX)
    assert "1101 McCulloch Blvd" not in out
    assert "Head to The Spot." in out


def test_all_contact_ungrounded_returns_clean_gap() -> None:
    text = "Their number is (775) 848-5418."
    out = redact_ungrounded_contact(text, _CTX)
    assert out == _UNGROUNDED_CONTACT_FALLBACK


def test_no_contact_info_untouched() -> None:
    text = "Saturday's street fair is the pick — that's where locals show up."
    assert redact_ungrounded_contact(text, _CTX) == text


def test_empty_context_drops_any_phone() -> None:
    text = "Reach them at (928) 555-0000."
    out = redact_ungrounded_contact(text, "")
    assert out == _UNGROUNDED_CONTACT_FALLBACK


def test_idempotent() -> None:
    text = "Go with Mudshark. Their listed number is (775) 848-5418."
    once = redact_ungrounded_contact(text, _CTX)
    twice = redact_ungrounded_contact(once, _CTX)
    assert once == twice
