"""Deterministic intent-phrase generator (Phase 2 Slice 2 — the "5k bank").

Expands sentence templates x dict slots (cuisines, services, areas, time
windows) into a labeled phrase bank, ``{intent_key: [phrases]}``. No LLM, no
API: the templates are hand-written natural phrasings; the slots come from the
same dictionaries the resolver routes with, so generated phrases exercise real
routing paths. Pipe the output through ``scripts/build_intent_phrase_bank.py``,
which keeps only phrases that provably route to their label against the current
resolver — failures in its report are resolver-coverage gaps to fix.

Usage:
    PYTHONPATH=. python scripts/generate_intent_phrases.py > /tmp/raw_bank.json
    PYTHONPATH=. python scripts/build_intent_phrase_bank.py /tmp/raw_bank.json
"""

from __future__ import annotations

import json

from app.chat.intents import dicts

# Conversational lead-ins. Kept short — every template is also emitted bare.
LEAD_INS = ("", "hey, ", "ok so ", "quick question - ")

# ---------------------------------------------------------------------------
# Per-intent templates. {x} = the slotted term, {area} = an area phrase.
# ---------------------------------------------------------------------------

EAT_TEMPLATES = (
    "where can i get {x}",
    "any good {x} places",
    "best {x} in town",
    "im craving {x}",
    "good {x} food",
    "looking for a {x} restaurant",
    "who has the best {x} around here",
    "{x} food near me",
    "wheres a good spot for {x}",
    "got any {x} recommendations",
    "{x} restaurant recommendations",
    "we want {x} tonight for dinner",
)
EAT_AREA_TEMPLATES = (
    "{x} food {area}",
    "good {x} {area}",
    "where can i get {x} {area}",
)
EAT_GENERIC = (
    "where should we eat",
    "good places to eat",
    "best restaurants in town",
    "im hungry where should i go for dinner",
    "any good restaurants around",
    "where to grab dinner",
    "lunch spots",
    "good food around here",
    "dinner recommendations",
    "we need takeout tonight for dinner",
    "best place for breakfast food",
    "casual dining options",
)
EAT_OPEN_NOW = (
    "anywhere to eat open right now",
    "what restaurants are open now",
    "food open late",
    "whos open for dinner right now",
    "any restaurants open now",
    "is anywhere open to eat right now",
    "restaurants open right now",
    "late night food open now",
)

SERVICE_TEMPLATES = (
    "i need a {x}",
    "find me a {x}",
    "any good {x} in town",
    "looking for a {x}",
    "can you recommend a {x}",
    "who is the best {x} around",
    "{x} recommendations",
    "i need a {x} asap",
    "got a {x} you can recommend",
    "best {x} in lake havasu",
    "need a reliable {x}",
    "is there a good {x} here",
)

EVENT_TODAY = (
    "what is happening today",
    "anything going on today",
    "whats going on tonight",
    "events today",
    "anything to do tonight",
    "what is there to do today",
    "whats happening tonight in town",
    "any events going on today",
    "things to do today",
    "live music tonight",
    "any concerts tonight",
    "whats on tonight",
)
EVENT_WEEKEND = (
    "what is happening this weekend",
    "events this weekend",
    "anything going on this weekend",
    "things to do this weekend",
    "whats on this weekend",
    "any events this weekend",
    "what should we do this weekend",
    "live music this weekend",
    "weekend events",
    "anything fun happening this weekend",
)
EVENT_THIS_WEEK = (
    "what is happening this week",
    "events this week",
    "anything going on this week",
    "things to do this week",
    "whats on this week",
    "any live music this week",
)
EVENT_NEXT_WEEK = (
    "what is happening next week",
    "events next week",
    "anything going on next week",
    "things to do next week",
    "whats on next week",
)
EVENT_UPCOMING = (
    "what events are coming up",
    "upcoming events",
    "any events coming up",
    "whats happening around town",
    "things to do in lake havasu",
    "what is going on around here",
    "any fun events soon",
    "whats happening",
)

GAS = (
    "cheapest gas in town",
    "where is the cheapest gas",
    "gas prices",
    "best gas prices",
    "lowest gas price around",
    "where should i get gas",
    "cheap gas near me",
    "cheapest diesel in town",
    "where is cheap fuel",
    "gas price check",
)

URGENT = tuple(
    t.format(x=s)
    for s in dicts.SYMPTOM_MAP
    for t in ("i need {x}", "where can i find {x}", "closest {x}", "{x} near me")
)

FITNESS = {
    "gym_fitness": ("gym", "fitness center", "crossfit", "a place to workout", "weights"),
    "yoga_pilates": ("yoga", "pilates", "a yoga studio", "barre class"),
    "martial_arts": ("martial arts", "karate", "jiu jitsu", "bjj", "a dojo", "taekwondo"),
    "pickleball": ("pickleball", "pickleball courts", "a tennis court"),
}
FITNESS_TEMPLATES = (
    "where can i do {x}",
    "any {x} around here",
    "looking for {x}",
    "is there {x} in town",
    "{x} near me",
    "best {x} in lake havasu",
    "i want to try {x}",
)

KIDS = (
    "swim lessons for kids",
    "classes for my 6 year old",
    "kids classes",
    "lessons for children",
    "any programs for youth",
    "activities classes for toddlers",
    "swim lessons for my kid",
    "art classes for kids",
    "dance lessons for children",
    "kids swim program",
)

LODGING = (
    "where should we stay",
    "good hotels in town",
    "best hotel in lake havasu",
    "any nice resorts",
    "rv parks around here",
    "campgrounds near the lake",
    "vacation rental recommendations",
    "cheap motels in town",
    "places to stay this weekend",
    "pet friendly hotels",
    "hotels near the lake",
    "where to stay with a big group",
)

WATER_RENTAL = (
    "where can i rent a boat",
    "boat rentals",
    "jet ski rental",
    "rent a pontoon boat",
    "kayak rentals near me",
    "paddleboard rental",
    "where do i rent a jet ski",
    "boat rental for the day",
    "waverunner rentals",
    "canoe rental",
)
WATER_REPAIR = (
    "boat repair",
    "boat mechanic in town",
    "who can fix my boat",
    "jet ski repair shop",
    "boat service near me",
    "marine mechanic",
)
WATER_GENERAL = (
    "where can i launch my boat",
    "boat ramps",
    "best marina in town",
    "fishing spots",
    "where to go fishing",
    "boat tours",
    "good fishing around here",
    "lake access points",
    "where can we kayak",
    "marina with fuel",
)

PARKS = (
    "good hiking trails",
    "best hikes around lake havasu",
    "parks for kids",
    "dog parks in town",
    "where can we go hiking",
    "best beaches",
    "beach access",
    "off road trails",
    "easy trails for beginners",
    "trailheads near town",
    "picnic parks",
    "skate parks",
)

CIVIC = (
    "churches in town",
    "where is the library",
    "post office hours",
    "dmv in lake havasu",
    "food bank near me",
    "community center programs",
    "city hall location",
    "senior center activities",
    "non profit organizations in town",
    "where can i go to church on sunday",
)

SHOPPING = (
    "where can i buy groceries",
    "grocery stores in town",
    "good shopping around here",
    "boutiques downtown",
    "where to buy souvenirs",
    "supermarket near me",
    "best places to shop",
    "where can i buy beach stuff",
    "farmers market shopping",
    "where to buy fishing gear",
)


def main() -> None:
    banks: dict[str, list[str]] = {}

    def add(intent: str, phrases) -> None:
        bank = banks.setdefault(intent, [])
        seen = {p.lower() for p in bank}
        for p in phrases:
            p = " ".join(str(p).split())
            if p.lower() not in seen:
                seen.add(p.lower())
                bank.append(p)

    def with_lead_ins(phrases) -> list[str]:
        out = []
        for p in phrases:
            for lead in LEAD_INS:
                out.append(f"{lead}{p}")
        return out

    # eat_find: cuisine x templates (+ areas), generic phrasings
    cuisines = [c for c in dicts.CUISINE_DICT if " " not in c or len(c) <= 12]
    eat: list[str] = list(EAT_GENERIC)
    for c in cuisines:
        eat.extend(t.format(x=c) for t in EAT_TEMPLATES)
    for c in cuisines[:8]:
        for area in list(dicts.AREA_DICT)[:6]:
            eat.extend(t.format(x=c, area=area) for t in EAT_AREA_TEMPLATES)
    add("eat_find", with_lead_ins(eat))
    add("eat_open_now", with_lead_ins(EAT_OPEN_NOW))

    # find_service: service x templates
    svc: list[str] = []
    for s in dicts.SERVICE_DICT:
        svc.extend(t.format(x=s) for t in SERVICE_TEMPLATES)
    add("find_service", with_lead_ins(svc))

    add("urgent_care", with_lead_ins(URGENT))
    add("cheapest_gas", with_lead_ins(GAS))
    add("events_today", with_lead_ins(EVENT_TODAY))
    add("events_weekend", with_lead_ins(EVENT_WEEKEND))
    add("events_this_week", with_lead_ins(EVENT_THIS_WEEK))
    add("events_next_week", with_lead_ins(EVENT_NEXT_WEEK))
    add("events_upcoming", with_lead_ins(EVENT_UPCOMING))

    for intent, terms in FITNESS.items():
        phrases = [t.format(x=x) for x in terms for t in FITNESS_TEMPLATES]
        add(intent, with_lead_ins(phrases))

    add("kids_lessons", with_lead_ins(KIDS))
    add("lodging_find", with_lead_ins(LODGING))
    add("boat_rental", with_lead_ins(WATER_RENTAL))
    add("boat_repair", with_lead_ins(WATER_REPAIR))
    add("on_the_water", with_lead_ins(WATER_GENERAL))
    add("parks_trails", with_lead_ins(PARKS))
    add("civic_resources", with_lead_ins(CIVIC))
    add("shopping_find", with_lead_ins(SHOPPING))

    total = sum(len(v) for v in banks.values())
    print(json.dumps({"banks": [{"intent": k, "phrases": v} for k, v in banks.items()]}, indent=1))
    import sys

    print(f"generated {total} phrases across {len(banks)} intents", file=sys.stderr)


if __name__ == "__main__":
    main()
