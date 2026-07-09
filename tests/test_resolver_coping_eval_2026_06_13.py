"""Committed resolver eval: coping questions vs. genuine browses.

Replaces the lost 296-question Cowork bank for the one classifier axis we keep
breaking — weather/coping asks ("when it's too hot", "stay cool", "beat the heat")
must NOT be claimed by the events / lodging / etc. browse branches; they should
fall through to Tier 3 for a real answer. Genuine event browses and lodging
lookups must still route as before. Pure (resolve() has no DB), so it runs in CI
as a fast regression gate for future intent-routing changes.
"""

from __future__ import annotations

from app.chat.intents.resolver import resolve

# Weather/coping asks — must not be routed to events or lodging.
COPING = [
    "what should I do when it is too hot",
    "what can I do to stay cool",
    "things to do to beat the heat",
    "how do I keep cool when it is hot",
    "where can I cool off when it is too hot",
    "what should we do when it's too hot out",
]

# Genuine event browses — must resolve to an events_* intent.
EVENT_BROWSES = [
    "what should I do this weekend",
    "what should we do tomorrow",
    "what's happening this week",
    "anything fun this weekend",
    "things to do tonight",
]

# Genuine lodging lookups — must resolve to lodging_find.
LODGING = [
    "where can I stay",
    "places to stay",
    "find me a hotel",
    "cheap hotels in town",
]


def _intent(query: str) -> str | None:
    r = resolve(query)
    return r.intent_key if r is not None else None


def test_coping_queries_not_routed_to_events_or_lodging() -> None:
    for q in COPING:
        k = _intent(q)
        assert k is None or (not k.startswith("events") and k != "lodging_find"), (q, k)


def test_event_browses_still_resolve_to_events() -> None:
    for q in EVENT_BROWSES:
        k = _intent(q)
        assert k is not None and k.startswith("events"), (q, k)


def test_lodging_lookups_still_resolve_to_lodging() -> None:
    for q in LODGING:
        assert _intent(q) == "lodging_find", q
