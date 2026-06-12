"""Unit tests for app.chat.tier3_postprocess._is_sentence_useful (F7) and the
grounding-scaffold leak scrub (P2-1, QA diagnostic 2026-06-12)."""

from __future__ import annotations

import pytest

from app.chat.tier3_postprocess import (
    _SCAFFOLDING_FALLBACK,
    _is_sentence_useful,
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
