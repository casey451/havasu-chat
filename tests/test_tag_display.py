"""Display-time event-tag filtering (site review §5)."""

from __future__ import annotations

from app.events.tag_display import public_event_tags


def test_drops_namespaced_taxonomy_keys() -> None:
    tags = [
        "family",
        "activity:trampoline",
        "music",
        "FACET:SPECIAL",
        "AUDIENCE:YOUTH",
        "sports",
    ]
    assert public_event_tags(tags) == ["family", "music", "sports"]


def test_preserves_order_and_friendly_tags() -> None:
    assert public_event_tags(["music", "free", "outdoor"]) == ["music", "free", "outdoor"]


def test_handles_none_and_blanks_and_non_strings() -> None:
    assert public_event_tags(None) == []
    assert public_event_tags([]) == []
    assert public_event_tags(["  ", None, 7, "family"]) == ["family"]


def test_strips_whitespace() -> None:
    assert public_event_tags(["  music  ", "activity:golf"]) == ["music"]
