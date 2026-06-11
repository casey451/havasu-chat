"""Tier-3 cache-key intent scoping (CHAT_DEEP_DIVE 2026-06-10 §1D fix).

The exact-key cache previously keyed on query text + onboarding hints + date
only — the same text classified under a different sub_intent/entity could
serve the other's cached answer. The fix threads sub_intent + entity into the
cache context and keys on the NORMALIZED query (so courtesy variants fold).
"""

from __future__ import annotations

import pytest

from app.chat.intent_classifier import IntentResult
from app.chat.llm_cache import make_cache_key


def _ir(**kw) -> IntentResult:
    base = dict(
        mode="ask",
        sub_intent="OPEN_ENDED",
        confidence=0.7,
        entity=None,
        raw_query="q",
        normalized_query="q",
        multi_domain_category_slugs=None,
    )
    base.update(kw)
    return IntentResult(**base)


def test_same_text_different_sub_intent_keys_differ():
    ctx_a = {"_today": "2026-06-11", "_sub_intent": "HOURS_LOOKUP"}
    ctx_b = {"_today": "2026-06-11", "_sub_intent": "LOCATION_LOOKUP"}
    assert make_cache_key("when is the parade", ctx_a) != make_cache_key(
        "when is the parade", ctx_b
    )


def test_same_text_different_entity_keys_differ():
    ctx_a = {"_today": "2026-06-11", "_entity": "mudshark brewery"}
    ctx_b = {"_today": "2026-06-11", "_entity": "barley brothers"}
    assert make_cache_key("are they open sunday", ctx_a) != make_cache_key(
        "are they open sunday", ctx_b
    )


def test_empty_intent_fields_fold_out_of_key():
    # _hash_context drops empty values, so a no-entity turn keys identically
    # whether the fields are absent or empty — no cache invalidation for the
    # common case.
    base = {"_today": "2026-06-11"}
    with_empty = {"_today": "2026-06-11", "_sub_intent": "", "_entity": ""}
    assert make_cache_key("best tacos", base) == make_cache_key("best tacos", with_empty)


def test_courtesy_variants_fold_to_one_key():
    ctx = {"_today": "2026-06-11"}
    assert make_cache_key("best tacos in lake havasu", ctx) == make_cache_key(
        "best tacos", ctx
    )


def test_handler_threads_intent_into_cache_context(monkeypatch):
    """answer_with_tier3 passes sub_intent/entity into the cache context and
    keys on the normalized query."""
    from app.chat import tier3_handler as t3

    captured: dict = {}

    def fake_make_cache_key(nq, ctx):
        captured["nq"] = nq
        captured["ctx"] = dict(ctx)
        return "test-key"

    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setattr(t3, "make_cache_key", fake_make_cache_key)
    monkeypatch.setattr(
        t3, "cache_lookup_with_embedding", lambda *a, **k: ("cached answer", None)
    )
    monkeypatch.setattr(
        t3, "build_context_and_rows_for_tier3", lambda *a, **k: ("", [])
    )

    ir = _ir(sub_intent="HOURS_LOOKUP", entity="Mudshark Brewery",
             raw_query="Are they open Sunday??", normalized_query="are they open sunday")

    class _DB:  # answer_with_tier3 only touches db via the stubbed callees here
        pass

    text, *_ = t3.answer_with_tier3("Are they open Sunday??", ir, _DB())
    assert text.startswith("cached answer")
    assert captured["nq"] == "are they open sunday"
    assert captured["ctx"].get("_sub_intent") == "HOURS_LOOKUP"
    assert captured["ctx"].get("_entity") == "mudshark brewery"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
