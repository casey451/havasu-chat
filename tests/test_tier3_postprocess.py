"""Unit tests for app.chat.tier3_postprocess._is_sentence_useful (F7)."""

from __future__ import annotations

import pytest

from app.chat.tier3_postprocess import _is_sentence_useful


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
