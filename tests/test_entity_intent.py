"""Unit tests for app.chat.entity_intent.near_match_subject_overlaps (F6)."""

from __future__ import annotations

import pytest

from app.chat.entity_intent import near_match_subject_overlaps


@pytest.mark.parametrize(
    ("query", "canonical", "expected"),
    [
        ("rating for Heat Hotel", "Heat Hotel", True),
        ("phone for mdshrkbrwry", "Mudshark Brewery", True),
        ("hotel near me", "Heat Hotel", True),
        ("place near me", "Heat Hotel", False),
        ("rating for Fabricated Hotel Name 555", "Heat Hotel", False),
        ("", "Heat Hotel", False),
    ],
)
def test_near_match_subject_overlaps_f6(query: str, canonical: str, expected: bool) -> None:
    assert near_match_subject_overlaps(query, canonical) is expected
