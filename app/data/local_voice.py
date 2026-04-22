"""Curated local-voice blurbs for Tier 3 (Phase 6.5-lite).

Each entry is a dict with:
- id (str): stable key
- keywords (list[str]): phrases matched with word boundaries against the user query
- category (str): free-form grouping for operators
- text (str): one line injected into the model payload
- context_tags (list[str], optional): session/query filters (kids_ok, adults_only, visitor_friendly, local_focused, evening, morning, weekend, free, cheap, pricy, expensive, …)
- season (str, optional): winter | spring_fall | summer | holiday | year_round (default: year_round)

Ships empty; operators append validated rows over time.
"""

from __future__ import annotations

from typing import Any

_VALID_SEASONS = frozenset({"winter", "spring_fall", "summer", "holiday", "year_round"})


def _validate_entry(entry: dict[str, Any]) -> None:
    if not isinstance(entry, dict):
        raise TypeError(f"local voice entry must be dict, got {type(entry)}")
    eid = entry.get("id")
    if not isinstance(eid, str) or not eid.strip():
        raise ValueError("local voice entry requires non-empty string id")
    kws = entry.get("keywords")
    if not isinstance(kws, list) or not kws:
        raise ValueError(f"local voice entry {eid!r} requires non-empty keywords list")
    for kw in kws:
        if not isinstance(kw, str) or not kw.strip():
            raise ValueError(f"local voice entry {eid!r} has invalid keyword {kw!r}")
    cat = entry.get("category")
    if not isinstance(cat, str) or not cat.strip():
        raise ValueError(f"local voice entry {eid!r} requires non-empty category")
    text = entry.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"local voice entry {eid!r} requires non-empty text")
    tags = entry.get("context_tags")
    if tags is not None:
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise ValueError(f"local voice entry {eid!r} context_tags must be list[str] or omitted")
    season = entry.get("season")
    if season is not None:
        if not isinstance(season, str) or season not in _VALID_SEASONS:
            raise ValueError(
                f"local voice entry {eid!r} season must be one of {_VALID_SEASONS}, got {season!r}"
            )


LOCAL_VOICE: list[dict[str, Any]] = []

for _row in LOCAL_VOICE:
    _validate_entry(_row)
