"""Tests for ``mention_scanner`` (Phase 5.5)."""

from __future__ import annotations

from app.contrib.mention_scanner import STOP_PHRASES, scan_tier3_response


def test_extracts_title_case_phrase() -> None:
    text = "You might enjoy Red Rock Cafe near the water."
    names = {c.mentioned_name for c in scan_tier3_response(text)}
    assert "Red Rock Cafe" in names


def test_filters_stop_phrases() -> None:
    text = "Lake Havasu City has many parks and Google Search works too."
    names = {c.mentioned_name.lower() for c in scan_tier3_response(text)}
    assert "lake havasu city" not in names
    assert "google search" not in names


def test_strips_urls_before_scan() -> None:
    text = "See https://www.GoLakeHavasu.com and also Marina Cantina nearby."
    names = {c.mentioned_name for c in scan_tier3_response(text)}
    assert "GoLakeHavasu" not in names
    assert "Marina Cantina" in names


def test_dedupes_repeated_phrase() -> None:
    text = "Foo Bar is nice. Many like Foo Bar for lunch."
    out = scan_tier3_response(text)
    assert len([c for c in out if c.mentioned_name == "Foo Bar"]) == 1


def test_single_word_not_matched() -> None:
    text = "Hospitality matters here."
    assert scan_tier3_response(text) == []


def test_scan_never_emits_more_than_five_words() -> None:
    text = "Alpha Beta Gamma Delta Epsilon Zeta is a long run of cap words."
    for c in scan_tier3_response(text):
        assert len(c.mentioned_name.split()) <= 5


def test_minimum_phrase_length_six() -> None:
    text = "Visit Local Hotspots Here Today."
    for c in scan_tier3_response(text):
        assert len(c.mentioned_name) >= 6


def test_empty_response() -> None:
    assert scan_tier3_response("") == []
    assert scan_tier3_response("   ") == []


def test_stop_phrases_frozenset_contains_expected() -> None:
    assert "Lake Havasu" in STOP_PHRASES
    assert "Convention Visitors Bureau" in STOP_PHRASES
