"""L3 fuzzy intent matching (Ask Hava intent catalog, Phase 2 Slice 3).

The L1/L2 resolver only claims a turn when a known keyword/phrase appears in
the query. Real users describe *needs* without naming the trade -- "my sink is
leaking", "locked out of my car", "someone to wrap my truck" -- and every one
of those used to fall through to the Tier 3 LLM. This layer closes that gap
with rapidfuzz token-set matching against a curated exemplar bank, mapping a
near-match to the SAME intent keys (and grounded slots) the L1/L2 layers use.

Design rules (mirrors the Phase 2 plan, Slice 3):

* **Conservative by construction.** Five guards run before any claim:
  an out-of-vocabulary token guard (a token that is neither category
  vocabulary, exemplar vocabulary, filler, locality, nor a number means the
  turn is probably about a named entity -- decline), a length guard (long
  messages are conversational), a score threshold, a cross-intent margin rule
  (ambiguous between two intents -> decline), and a never-finalize set
  (``urgent_care`` / ``cheapest_gas`` may only be claimed by the exact L1/L2
  layers -- a fuzzy guess on an urgent-care or price query is worse than the
  fall-through).
* **Fall-through is the failure mode.** Any doubt, any exception -> ``None``
  -> the existing Tier 2 / Tier 3 path answers exactly as before.
* **Flags.** ``INTENT_L3_FUZZY`` is a kill switch (default ON; set "0"/
  "false"/"no"/"off" to make the resolver byte-identical to pre-L3).
  ``INTENT_L3_SHADOW`` (default OFF) logs every would-be claim and returns
  ``None`` -- threshold tuning on real traffic with zero behavior change.
* **No imports from resolver/runtime** (they import us). The caller passes
  the live category vocabulary in; the guard sets here are deliberately
  self-contained copies.
"""

from __future__ import annotations

import logging
import os
import re
from typing import NamedTuple

from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)

_FLAG_ENV = "INTENT_L3_FUZZY"
_SHADOW_ENV = "INTENT_L3_SHADOW"

# Score threshold (token_set_ratio, 0-100) and the minimum lead the winning
# intent must hold over the best-scoring OTHER intent. Tuned conservatively;
# INTENT_L3_SHADOW exists so these can be re-tuned from real match logs.
THRESHOLD = 88
MARGIN = 4

# Queries longer than this are conversations, not lookups -- decline.
_MAX_TOKENS = 12
_MAX_CHARS = 90

# Intents the fuzzy layer must never finalize (Phase 2 plan: propose-only).
# urgent_care: a wrong fuzzy match on a health query is a trust failure.
# cheapest_gas: price utilities must only fire on the exact ask.
NEVER_FINALIZE = frozenset({"urgent_care", "cheapest_gas"})

# Self-contained filler/locality guards (runtime has equivalents, but importing
# runtime here would create an import cycle -- see module docstring).
_FILLER_TOKENS: frozenset[str] = frozenset(
    """a again an and any anywhere are around asap at best can cheap cheapest
    close closed could currently do does find for from get good great hava have
    help hey hi how i im in is it its late me my myself near nearby need new
    now of ok okay on open or our ourselves please right should so some
    somebody someone something somewhere still that the there this to today
    tonight tomorrow top town up us we week weekend what when where which who
    whose why will with would you your""".split()
)
_LOCALITY_TOKENS: frozenset[str] = frozenset(
    {"lake", "havasu", "city", "arizona", "az", "lhc"}
)

_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def _area_tokens() -> frozenset[str]:
    # Neighborhood words ("downtown", "english village") are legitimate query
    # tokens — the resolver layers them back in as the ``area`` slot.
    from app.chat.intents import dicts

    out: set[str] = set()
    for phrase in dicts.AREA_DICT:
        out.update(t for t in _TOKEN_RE.split(phrase) if t)
    return frozenset(out)


_AREA_TOKENS: frozenset[str] = _area_tokens()


class Exemplar(NamedTuple):
    phrase: str
    intent: str
    slots: tuple[tuple[str, str], ...] = ()


def _svc(phrase: str, service: str) -> Exemplar:
    """find_service exemplar with a fixed service slot (must be a SERVICE_DICT key)."""
    return Exemplar(phrase, "find_service", (("service", service),))


# ---------------------------------------------------------------------------
# Exemplar bank. Phrases are written the way ``normalize()`` would emit them
# (lowercase, no edge punctuation). Each maps to a real intent key; service
# slots are real SERVICE_DICT keys (tests assert referential integrity).
# "_events" is a pseudo-key the resolver converts through its existing
# event-window logic so "live bands tonight" lands on events_today, etc.
# ---------------------------------------------------------------------------
EXEMPLARS: tuple[Exemplar, ...] = (
    # -- plumbing --
    _svc("my sink is leaking", "plumber"),
    _svc("leaky faucet", "plumber"),
    _svc("clogged toilet", "plumber"),
    _svc("clogged drain", "plumber"),
    _svc("water heater is broken", "plumber"),
    _svc("burst pipe", "plumber"),
    _svc("slab leak", "plumber"),
    _svc("garbage disposal is jammed", "plumber"),
    # -- electrical --
    _svc("outlet stopped working", "electrician"),
    _svc("breaker keeps tripping", "electrician"),
    _svc("install a ceiling fan", "electrician"),
    _svc("light switch not working", "electrician"),
    # -- hvac --
    _svc("my ac is out", "hvac"),
    _svc("ac stopped working", "hvac"),
    _svc("ac is not blowing cold", "hvac"),
    _svc("air conditioner is broken", "hvac"),
    _svc("heater not working", "hvac"),
    _svc("swamp cooler service", "hvac"),
    # -- roofing --
    _svc("my roof is leaking", "roofer"),
    _svc("roof leak", "roofer"),
    _svc("need a new roof", "roofer"),
    # -- handyman / small jobs --
    _svc("fix things around the house", "handyman"),
    _svc("odd jobs around the house", "handyman"),
    _svc("mount a tv on the wall", "handyman"),
    # -- landscaping --
    _svc("mow my lawn", "landscaper"),
    _svc("yard work", "landscaper"),
    _svc("yard cleanup", "landscaper"),
    _svc("weed control", "landscaper"),
    _svc("desert landscaping", "landscaper"),
    # -- tree work --
    _svc("remove a tree", "tree service"),
    _svc("palm tree trimming", "tree service"),
    _svc("stump grinding", "tree service"),
    # -- pest control --
    _svc("scorpions in my house", "pest control"),
    _svc("bug spraying", "pest control"),
    _svc("termite inspection", "pest control"),
    _svc("bee removal", "pest control"),
    _svc("exterminator", "pest control"),
    # -- pool --
    _svc("pool is green", "pool service"),
    _svc("fix my pool pump", "pool service"),
    _svc("weekly pool cleaning", "pool service"),
    # -- painting --
    _svc("paint my house", "painter"),
    _svc("interior painting", "painter"),
    # -- appliance --
    _svc("my fridge stopped working", "appliance repair"),
    _svc("refrigerator is not cooling", "appliance repair"),
    _svc("washer is broken", "appliance repair"),
    _svc("dryer not heating", "appliance repair"),
    _svc("dishwasher is broken", "appliance repair"),
    # -- garage door --
    _svc("garage door will not open", "garage door"),
    _svc("garage door spring broke", "garage door"),
    _svc("garage door opener install", "garage door"),
    # -- junk / hauling --
    _svc("haul away junk", "junk removal"),
    _svc("get rid of old furniture", "junk removal"),
    _svc("junk pickup", "junk removal"),
    _svc("clean out my garage", "junk removal"),
    # -- pressure washing --
    _svc("pressure wash my driveway", "pressure washing"),
    _svc("power wash my house", "pressure washing"),
    # -- septic --
    _svc("septic tank pumping", "septic"),
    _svc("get my septic pumped", "septic"),
    # -- welding --
    _svc("custom metal work", "welding"),
    _svc("welding and fabrication", "welding"),
    # -- screens / shade --
    _svc("patio cover installation", "patio covers"),
    _svc("sun screens for my windows", "sun screens"),
    _svc("awning installation", "patio covers"),
    # -- mobile home --
    _svc("mobile home leveling", "mobile home repair"),
    _svc("skirting for my mobile home", "mobile home repair"),
    # -- locksmith --
    _svc("locked out of my house", "locksmith"),
    _svc("locked out of my car", "locksmith"),
    _svc("locked my keys in the car", "locksmith"),
    _svc("rekey my locks", "locksmith"),
    _svc("make a spare key", "locksmith"),
    # -- moving --
    _svc("help moving furniture", "movers"),
    _svc("moving company", "movers"),
    # -- solar --
    _svc("solar panel installation", "solar"),
    _svc("solar quote for my house", "solar"),
    # -- auto: mechanic / tires / body / glass / tint / wrap / detail / tow --
    _svc("my car will not start", "mechanic"),
    _svc("car is making a weird noise", "mechanic"),
    _svc("check engine light is on", "mechanic"),
    _svc("brake repair", "mechanic"),
    _svc("flat tire", "tires"),
    _svc("new tires", "tires"),
    _svc("tire rotation", "tires"),
    _svc("fender bender repair", "auto body"),
    _svc("dent removal", "auto body"),
    _svc("cracked windshield", "auto glass"),
    _svc("windshield replacement", "auto glass"),
    _svc("rock chip repair", "auto glass"),
    _svc("tint my windows", "window tint"),
    _svc("window tinting for my truck", "window tint"),
    _svc("wrap my vehicle", "vehicle wraps"),
    _svc("wrap my truck", "vehicle wraps"),
    _svc("get my van wrapped", "vehicle wraps"),
    _svc("detail my car", "detailing"),
    _svc("detail my boat", "detailing"),
    _svc("boat detail and wash", "detailing"),
    _svc("interior detailing", "detailing"),
    _svc("mobile detailing", "detailing"),
    _svc("my car broke down", "towing"),
    _svc("need a tow", "towing"),
    _svc("get my car towed", "towing"),
    # -- golf carts --
    _svc("golf cart repair", "golf cart"),
    _svc("buy a golf cart", "golf cart"),
    _svc("golf cart batteries", "golf cart"),
    # -- trailer -- ("fix my boat trailer" stays with the L1 boat_repair
    # bucket: boat shops fix boat trailers, and the water branch owns it)
    _svc("trailer repair", "trailer repair"),
    # -- pets --
    _svc("my dog is sick", "vet"),
    _svc("my cat is sick", "vet"),
    _svc("puppy shots", "vet"),
    _svc("spay and neuter", "vet"),
    _svc("someone to watch my dog", "pet sitting"),
    _svc("watch my dog while we are out of town", "pet sitting"),
    _svc("dog sitter", "pet sitting"),
    _svc("cat sitter", "pet sitting"),
    _svc("dog walking", "pet sitting"),
    _svc("dog poop cleanup", "pet waste removal"),
    _svc("pooper scooper service", "pet waste removal"),
    # -- beauty / personal care --
    _svc("get a haircut", "barber"),
    _svc("haircut for my son", "barber"),
    _svc("color my hair", "salon"),
    _svc("highlights and a trim", "salon"),
    _svc("get my nails done", "nails"),
    _svc("manicure and pedicure", "nails"),
    _svc("get a massage", "massage"),
    _svc("couples massage", "massage"),
    _svc("get a facial", "spa"),
    _svc("get a tattoo", "tattoo"),
    # -- health (listing-only) --
    _svc("teeth cleaning", "dentist"),
    _svc("get a tooth pulled", "dentist"),
    _svc("get new glasses", "eye doctor"),
    # ("contacts prescription" deliberately absent: the symptom branch owns
    # "prescription" and a pharmacy listing is the established answer)
    _svc("hearing aid repair", "hearing aids"),
    _svc("get my hearing checked", "hearing aids"),
    _svc("talk to a counselor", "counselor"),
    _svc("see a therapist", "counselor"),
    # -- professional --
    _svc("do my taxes", "accountant"),
    _svc("file my taxes", "accountant"),
    _svc("need legal help", "lawyer"),
    _svc("divorce lawyer", "lawyer"),
    _svc("get something notarized", "notary"),
    _svc("manage my rental property", "property management"),
    # ("vacation rental management" deliberately absent: "vacation rental" is
    # a lodging word at L1, and the lodging browse is the established answer)
    _svc("wash and fold service", "laundromat"),
    _svc("coin laundry", "laundromat"),
    _svc("get my suit dry cleaned", "dry cleaning"),
    _svc("fix my computer", "computer repair"),
    _svc("laptop screen repair", "computer repair"),
    _svc("cracked phone screen", "phone repair"),
    _svc("business signs", "sign shop"),
    _svc("banner printing", "sign shop"),
    _svc("print business cards", "print shop"),
    _svc("plan a wedding", "event planner"),
    _svc("ship a package", "shipping"),
    # -- funeral --
    _svc("funeral arrangements", "funeral home"),
    _svc("cremation services", "funeral home"),
    # -- propane --
    _svc("propane refill", "propane"),
    _svc("fill my propane tank", "propane"),
    # -- eat & drink --
    Exemplar("grab a bite", "eat_find"),
    Exemplar("a bite to eat", "eat_find"),
    Exemplar("date night spot", "eat_find"),
    Exemplar("watch the game somewhere", "eat_find", (("cuisine", "sports bar"),)),
    Exemplar("drinks with friends", "eat_find", (("cuisine", "bar"),)),
    # -- events (resolver converts "_events" through its window logic) --
    Exemplar("live bands", "_events"),
    Exemplar("live entertainment", "_events"),
    Exemplar("karaoke night", "_events"),
    Exemplar("trivia night", "_events"),
    Exemplar("car show", "_events"),
    Exemplar("craft fair", "_events"),
    # -- lodging --
    Exemplar("book a room", "lodging_find"),
    Exemplar("book a room for the weekend", "lodging_find"),
    # -- on the water --
    Exemplar("rent a pontoon", "boat_rental"),
    Exemplar("pontoon rental", "boat_rental"),
    Exemplar("rent jet skis", "boat_rental"),
    Exemplar("launch my boat", "on_the_water"),
    # -- parks / outdoors --
    Exemplar("take the kids to a playground", "parks_trails"),
    Exemplar("splash pad", "parks_trails"),
    Exemplar("watch the sunset", "parks_trails"),
    # -- civic --
    Exemplar("food assistance", "civic_resources"),
    Exemplar("soup kitchen", "civic_resources"),
    Exemplar("renew my registration", "civic_resources"),
    Exemplar("register to vote", "civic_resources"),
    # -- shopping --
    Exemplar("souvenirs", "shopping_find"),
    Exemplar("buy a swimsuit", "shopping_find"),
    Exemplar("buy a gun", "shopping_find"),
    # -- kids -- ("stuff for the kids to do" deliberately absent: the "to do"
    # event words own that shape, and the events listing is the right answer)
    Exemplar("activities for my kids", "kids_lessons", (("age_band", "kids"),)),
)


def is_enabled() -> bool:
    # Default ON; explicit "0"/"false"/"no"/"off" is the kill switch (same
    # polarity as USE_INTENT_LAYER so ops muscle memory transfers).
    return (os.environ.get(_FLAG_ENV) or "").strip().lower() not in ("0", "false", "no", "off")


def is_shadow() -> bool:
    return (os.environ.get(_SHADOW_ENV) or "").strip().lower() in ("1", "true", "yes", "on")


_PHRASES: tuple[str, ...] = tuple(e.phrase for e in EXEMPLARS)

# Tokens contributed by the exemplar phrases themselves. A query token that is
# category vocab, exemplar vocab, filler, locality, or numeric is "explained";
# anything else (e.g. "mudshark") marks the turn as entity-ish -> decline.
_EXEMPLAR_TOKENS: frozenset[str] = frozenset(
    tok for e in EXEMPLARS for tok in _TOKEN_RE.split(e.phrase) if tok
)


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.split(text or "") if t]


def _has_unknown_token(tokens: list[str], base_vocab: frozenset[str]) -> bool:
    for tok in tokens:
        if tok.isdigit():
            continue
        if (
            tok in _FILLER_TOKENS
            or tok in _LOCALITY_TOKENS
            or tok in _EXEMPLAR_TOKENS
            or tok in _AREA_TOKENS
        ):
            continue
        if tok in base_vocab or (tok.endswith("s") and tok[:-1] in base_vocab) or (tok + "s") in base_vocab:
            continue
        return True
    return False


def match_l3(t: str, base_vocab: frozenset[str]) -> tuple[str, dict[str, object]] | None:
    """Best fuzzy intent for normalized query ``t``, or ``None`` to fall through.

    Returns ``(intent_key, fixed_slots)``; the caller (resolver) layers dynamic
    slots (area / open_now / window / ...) on top and stamps layer "L3".
    """
    if not is_enabled():
        return None
    if not t or len(t) > _MAX_CHARS:
        return None
    toks = _tokens(t)
    if not toks or len(toks) > _MAX_TOKENS:
        return None
    if _has_unknown_token(toks, base_vocab):
        return None

    try:
        matches = process.extract(
            t,
            _PHRASES,
            scorer=fuzz.token_set_ratio,
            score_cutoff=THRESHOLD,
            limit=8,
        )
    except Exception:  # pragma: no cover -- rapidfuzz never raises in practice
        logger.exception("intent_l3: rapidfuzz extract failed")
        return None
    if not matches:
        return None

    # Best score per intent (matches arrive score-desc).
    best_by_intent: dict[str, tuple[float, Exemplar]] = {}
    for _phrase, score, idx in matches:
        ex = EXEMPLARS[idx]
        cur = best_by_intent.get(ex.intent)
        if cur is None or score > cur[0]:
            best_by_intent[ex.intent] = (float(score), ex)

    ranked = sorted(best_by_intent.items(), key=lambda kv: kv[1][0], reverse=True)
    top_intent, (top_score, top_ex) = ranked[0]
    if len(ranked) > 1:
        second_score = ranked[1][1][0]
        if top_score - second_score < MARGIN:
            logger.info(
                "intent_l3: ambiguous %r (%s=%.0f vs %s=%.0f) -> fall through",
                t, top_intent, top_score, ranked[1][0], second_score,
            )
            return None

    if top_intent in NEVER_FINALIZE:
        logger.info(
            "intent_l3: %r matched never-finalize intent %s (%.0f) -> fall through",
            t, top_intent, top_score,
        )
        return None

    if is_shadow():
        logger.info(
            "intent_l3_shadow: would claim %r -> %s via %r (%.0f)",
            t, top_intent, top_ex.phrase, top_score,
        )
        return None

    logger.info(
        "intent_l3: claimed %r -> %s via %r (%.0f)", t, top_intent, top_ex.phrase, top_score
    )
    return top_intent, dict(top_ex.slots)
