"""Copy audit §5b — review excerpts ordered by recency, not API order.

The profile shows the first 3 snippets; Google's array order is arbitrary,
which let a years-old towing complaint lead a listing. Newest-first keeps
everything visible (real data or nothing) while the freshest voices speak
first. Pure-function tests — no DB.
"""

from __future__ import annotations

from app.providers.view_models import _snippet_publish_dt, _snippets_newest_first


def _s(text: str, publish_time: str | None) -> dict:
    return {"author": "A", "rating": 4, "text": text, "publish_time": publish_time}


def test_newest_first_reorders_api_order():
    old = _s("old complaint", "2023-01-05T12:00:00Z")
    mid = _s("middling", "2025-06-01T08:30:00Z")
    new = _s("fresh take", "2026-06-01T19:45:00Z")
    out = _snippets_newest_first([old, mid, new])
    assert [x["text"] for x in out] == ["fresh take", "middling", "old complaint"]


def test_undated_snippets_sink_but_survive_in_original_order():
    a = _s("undated A", None)
    b = _s("dated", "2026-01-01T00:00:00Z")
    c = _s("undated C", "not-a-timestamp")
    out = _snippets_newest_first([a, b, c])
    assert [x["text"] for x in out] == ["dated", "undated A", "undated C"]


def test_stable_for_equal_timestamps():
    t = "2026-03-03T03:03:03Z"
    out = _snippets_newest_first([_s("first", t), _s("second", t)])
    assert [x["text"] for x in out] == ["first", "second"]


def test_parser_handles_google_fractional_digits_and_garbage():
    # Google emits 7–9 fractional digits; fromisoformat wants <=6.
    assert _snippet_publish_dt(_s("x", "2026-06-01T19:45:00.123456789Z")) is not None
    assert _snippet_publish_dt(_s("x", "2026-06-01T19:45:00Z")) is not None
    assert _snippet_publish_dt(_s("x", "")) is None
    assert _snippet_publish_dt(_s("x", None)) is None
    assert _snippet_publish_dt("not-a-dict") is None


def test_empty_list_is_fine():
    assert _snippets_newest_first([]) == []
