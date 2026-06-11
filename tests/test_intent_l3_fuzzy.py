"""L3 fuzzy layer (Slice 3) — behavior, guards, flags, exemplar integrity.

DB-free: resolver + fuzzy are pure. The L3 layer must only ever widen coverage
for queries the L1/L2 layers DECLINED; anything they already claim is asserted
byte-identical by tests/test_intent_phrase_bank.py (the 5.6k gate).
"""

from __future__ import annotations

import pytest

from app.chat.intents import dicts, fuzzy
from app.chat.intents.resolver import L3, category_vocabulary, resolve


@pytest.fixture(autouse=True)
def _l3_on(monkeypatch):
    monkeypatch.delenv("INTENT_L3_FUZZY", raising=False)
    monkeypatch.delenv("INTENT_L3_SHADOW", raising=False)


# ---------------------------------------------------------------------------
# Coverage: colloquial need-phrasings that previously fell through to Tier 3.
# ---------------------------------------------------------------------------

L3_CASES = [
    ("my sink is leaking", "find_service", {"service": "plumber"}),
    ("the sink is leaking again", "find_service", {"service": "plumber"}),
    ("my ac is out", "find_service", {"service": "hvac"}),
    ("locked out of my car", "find_service", {"service": "locksmith"}),
    ("locked myself out of the house", "find_service", {"service": "locksmith"}),
    ("someone to wrap my vehicle", "find_service", {"service": "vehicle wraps"}),
    ("boat detail and wash", "find_service", {"service": "detailing"}),
    # "windshield" is itself a SERVICE_DICT key, so L1 claims this one with
    # the matched term as the slot — same listing, cheaper layer.
    ("cracked windshield", "find_service", {"service": "windshield"}),
    ("my car will not start", "find_service", {"service": "mechanic"}),
    ("haul away junk", "find_service", {"service": "junk removal"}),
    ("scorpions in my house", "find_service", {"service": "pest control"}),
    ("mow my lawn", "find_service", {"service": "landscaper"}),
    ("my fridge stopped working", "find_service", {"service": "appliance repair"}),
    ("garage door will not open", "find_service", {"service": "garage door"}),
    ("someone to watch my dog", "find_service", {"service": "pet sitting"}),
    ("get a haircut", "find_service", {"service": "barber"}),
    ("do my taxes", "find_service", {"service": "accountant"}),
    ("get something notarized", "find_service", {"service": "notary"}),
    ("wash and fold service", "find_service", {"service": "wash and fold"}),
    ("fix my computer", "find_service", {"service": "computer repair"}),
    ("funeral arrangements", "find_service", {"service": "funeral"}),
    ("grab a bite", "eat_find", {}),
    ("drinks with friends", "eat_find", {"cuisine": "bar"}),
    ("rent a pontoon", "boat_rental", {}),
    ("book a room", "lodging_find", {}),
    ("food assistance", "civic_resources", {}),
    ("souvenirs", "shopping_find", {}),
]


@pytest.mark.parametrize("query,intent,expected_slots", L3_CASES,
                         ids=[c[0][:32] for c in L3_CASES])
def test_l3_claims_paraphrase(query, intent, expected_slots):
    resolved = resolve(query)
    assert resolved is not None, f"{query!r} fell through"
    assert resolved.intent_key == intent
    for k, v in expected_slots.items():
        assert resolved.slots.get(k) == v, (k, resolved.slots)


def test_l3_layer_is_stamped():
    resolved = resolve("my sink is leaking")
    assert resolved is not None and resolved.layer == L3


def test_l3_events_pseudo_intent_uses_window_logic():
    resolved = resolve("karaoke night tonight")
    assert resolved is not None
    assert resolved.intent_key == "events_today"
    assert resolved.slots.get("window") == "today"
    resolved2 = resolve("karaoke night")
    assert resolved2 is not None
    assert resolved2.intent_key == "events_upcoming"


def test_l3_layers_dynamic_slots_on_top():
    resolved = resolve("my sink is leaking downtown")
    assert resolved is not None
    assert resolved.intent_key == "find_service"
    assert resolved.slots.get("service") == "plumber"
    assert resolved.slots.get("area") == "Downtown"


# ---------------------------------------------------------------------------
# Guards.
# ---------------------------------------------------------------------------


def test_unknown_token_declines():
    # "mudshark" is no part of any vocabulary -> entity-ish -> decline.
    vocab = category_vocabulary()
    assert fuzzy.match_l3("mudshark sink is leaking", vocab) is None


def test_long_queries_decline():
    vocab = category_vocabulary()
    long_q = "my sink is leaking and also i was wondering about the weather and the lake and everything else"
    assert fuzzy.match_l3(long_q, vocab) is None


def test_never_finalize_intents_cannot_claim_at_l3():
    for ex in fuzzy.EXEMPLARS:
        assert ex.intent not in fuzzy.NEVER_FINALIZE, (
            f"exemplar {ex.phrase!r} maps to never-finalize intent {ex.intent}"
        )
    # And the exact-layer paths still own them (L1/L2, not L3).
    gas = resolve("cheapest gas")
    assert gas is not None and gas.intent_key == "cheapest_gas" and gas.layer != L3
    uc = resolve("i need a walk in clinic")
    assert uc is not None and uc.intent_key == "urgent_care" and uc.layer != L3


def test_gibberish_declines():
    assert resolve("asdf qwerty zxcv") is None


# ---------------------------------------------------------------------------
# Flags.
# ---------------------------------------------------------------------------


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("INTENT_L3_FUZZY", "0")
    assert resolve("my sink is leaking") is None  # byte-identical to pre-L3


def test_shadow_mode_logs_but_does_not_claim(monkeypatch):
    # Stub the module logger instead of caplog: alembic's fileConfig (run by
    # the DB fixture) disables existing loggers, so records never propagate.
    monkeypatch.setenv("INTENT_L3_SHADOW", "1")
    calls: list[str] = []

    class _Stub:
        def info(self, msg, *args):
            calls.append(msg % args if args else msg)

        def exception(self, *a, **k):  # pragma: no cover
            calls.append("exception")

    monkeypatch.setattr(fuzzy, "logger", _Stub())
    assert resolve("my sink is leaking") is None
    assert any("intent_l3_shadow" in c for c in calls)


# ---------------------------------------------------------------------------
# Exemplar bank integrity.
# ---------------------------------------------------------------------------


def test_every_exemplar_resolves_to_its_own_intent():
    """Each exemplar phrase, fed through the FULL resolver, must land on its
    own intent (any layer) — guarding against an L1/L2 branch hijacking an
    exemplar to a different intent."""
    for ex in fuzzy.EXEMPLARS:
        resolved = resolve(ex.phrase)
        assert resolved is not None, f"exemplar {ex.phrase!r} fell through"
        expected = ex.intent
        if expected == "_events":
            assert resolved.intent_key.startswith("events_"), (
                f"{ex.phrase!r} -> {resolved.intent_key}"
            )
        else:
            assert resolved.intent_key == expected, (
                f"{ex.phrase!r} -> {resolved.intent_key}, expected {expected}"
            )


def test_service_slots_reference_real_dict_keys():
    for ex in fuzzy.EXEMPLARS:
        for k, v in ex.slots:
            if k == "service":
                assert v in dicts.SERVICE_DICT, f"{ex.phrase!r} -> unknown service {v!r}"
            if k == "cuisine":
                assert v in dicts.CUISINE_DICT, f"{ex.phrase!r} -> unknown cuisine {v!r}"


def test_exemplar_phrases_unique():
    phrases = [e.phrase for e in fuzzy.EXEMPLARS]
    assert len(phrases) == len(set(phrases))
