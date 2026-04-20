"""Parameterized tests for ``app.chat.intent_classifier`` (Phase 2.1)."""

from __future__ import annotations

import pytest

from app.chat.intent_classifier import IntentResult, classify

# (query, expected_mode, expected_sub_intent) — ~80 rows per Phase 2.1 spec.
_CLASSIFY_FIXTURES: list[tuple[str, str, str]] = [
    # --- ask: DATE_LOOKUP (5) ---
    ("When is the fireworks show?", "ask", "DATE_LOOKUP"),
    ("When are karate classes?", "ask", "DATE_LOOKUP"),
    ("What dates is the BMX race?", "ask", "DATE_LOOKUP"),
    ("When does little league start?", "ask", "DATE_LOOKUP"),
    ("When is the next farmers market date?", "ask", "NEXT_OCCURRENCE"),
    # --- ask: TIME_LOOKUP (5) ---
    ("What time does the class start?", "ask", "TIME_LOOKUP"),
    ("What time is gymnastics?", "ask", "TIME_LOOKUP"),
    ("Opening time for the aquatic center?", "ask", "TIME_LOOKUP"),
    ("Closing time tonight?", "ask", "TIME_LOOKUP"),
    ("Start time for the fireworks?", "ask", "TIME_LOOKUP"),
    # --- ask: LOCATION_LOOKUP (5) ---
    ("Where is Lake Havasu City BMX?", "ask", "LOCATION_LOOKUP"),
    ("Located address for sonics gymnastics?", "ask", "LOCATION_LOOKUP"),
    ("Location of the tap room jiu jitsu?", "ask", "LOCATION_LOOKUP"),
    ("Where can I find altitude trampoline?", "ask", "LOCATION_LOOKUP"),
    ("What is the address for havasu lanes?", "ask", "LOCATION_LOOKUP"),
    # --- ask: COST_LOOKUP (5) ---
    ("How much does a trampoline session cost at altitude?", "ask", "COST_LOOKUP"),
    ("What is the pricing for swim lessons?", "ask", "COST_LOOKUP"),
    ("Cost for little league signup?", "ask", "COST_LOOKUP"),
    ("Fees for the junior ranger program?", "ask", "COST_LOOKUP"),
    ("How much is bowling at havasu lanes?", "ask", "COST_LOOKUP"),
    # --- ask: PHONE_LOOKUP (5) ---
    ("Phone number for the aquatic center?", "ask", "PHONE_LOOKUP"),
    ("Call them at lions fc — what is the number?", "ask", "PHONE_LOOKUP"),
    ("Contact number for black belt academy?", "ask", "PHONE_LOOKUP"),
    ("I need the phone for ballet havasu.", "ask", "PHONE_LOOKUP"),
    ("What number should I call for flips for fun?", "ask", "PHONE_LOOKUP"),
    # --- ask: HOURS_LOOKUP (8) — avoid open-now phrases ---
    ("What are the hours for iron wolf golf?", "ask", "HOURS_LOOKUP"),
    ("Hours for bridge city combat?", "ask", "HOURS_LOOKUP"),
    ("When does havasu lanes close — hours?", "ask", "HOURS_LOOKUP"),
    ("Business hours for aqua beginnings?", "ask", "HOURS_LOOKUP"),
    ("What hours is the tap room open?", "ask", "HOURS_LOOKUP"),
    ("Is altitude open late on friday?", "ask", "HOURS_LOOKUP"),
    ("Is sonics open early on monday?", "ask", "HOURS_LOOKUP"),
    ("What time does altitude close on friday?", "ask", "TIME_LOOKUP"),
    # --- ask: WEBSITE_LOOKUP (5) ---
    ("Website for lake havasu little league?", "ask", "WEBSITE_LOOKUP"),
    ("What is the URL for lions fc?", "ask", "WEBSITE_LOOKUP"),
    ("Web address for the BMX track?", "ask", "WEBSITE_LOOKUP"),
    ("Site for universal gymnastics sonics?", "ask", "WEBSITE_LOOKUP"),
    ("Do you have the website for iron wolf?", "ask", "WEBSITE_LOOKUP"),
    # --- ask: AGE_LOOKUP (5) ---
    ("What age groups does sonics accept?", "ask", "AGE_LOOKUP"),
    ("Age requirements for junior ranger?", "ask", "AGE_LOOKUP"),
    ("How old does my kid need to be for little league?", "ask", "AGE_LOOKUP"),
    ("Youngest age for swim lessons at the aquatic center?", "ask", "AGE_LOOKUP"),
    ("Age range for flips for fun gymnastics?", "ask", "AGE_LOOKUP"),
    # --- ask: LIST_BY_CATEGORY (5) ---
    ("Any good soccer leagues in Lake Havasu?", "ask", "LIST_BY_CATEGORY"),
    ("What karate classes are available for kids?", "ask", "LIST_BY_CATEGORY"),
    ("Show me all swim lessons in town.", "ask", "LIST_BY_CATEGORY"),
    ("Find gymnastics programs for beginners.", "ask", "LIST_BY_CATEGORY"),
    ("What basketball programs exist here?", "ask", "LIST_BY_CATEGORY"),
    # --- ask: NEXT_OCCURRENCE (4) ---
    ("When is the next BMX race?", "ask", "NEXT_OCCURRENCE"),
    ("When's the next fireworks show?", "ask", "NEXT_OCCURRENCE"),
    ("Next class at sonics?", "ask", "NEXT_OCCURRENCE"),
    ("Next game for lions fc?", "ask", "NEXT_OCCURRENCE"),
    # --- ask: OPEN_NOW (4) ---
    ("Is altitude open right now?", "ask", "OPEN_NOW"),
    ("Is the BMX track open now?", "ask", "OPEN_NOW"),
    ("Is sonics currently open?", "ask", "OPEN_NOW"),
    ("Are you open now at havasu lanes?", "ask", "OPEN_NOW"),
    # --- ask: OPEN_ENDED (4) ---
    ("What is fun to do with kids this weekend?", "ask", "OPEN_ENDED"),
    ("Tell me about lake havasu activities.", "ask", "OPEN_ENDED"),
    ("We are visiting for two days — ideas?", "ask", "OPEN_ENDED"),
    ("Anything happening downtown tonight?", "ask", "OPEN_ENDED"),
    # --- contribute: NEW_EVENT (5) ---
    ("There is a car show at the channel Saturday at 6.", "contribute", "NEW_EVENT"),
    ("We are having a charity 5k on Sunday morning.", "contribute", "NEW_EVENT"),
    ("I want to add a concert at the park on Friday at 8pm.", "contribute", "NEW_EVENT"),
    ("There is an art walk happening this weekend downtown.", "contribute", "NEW_EVENT"),
    ("I am hosting a movie night Saturday at 7.", "contribute", "NEW_EVENT"),
    # --- contribute: NEW_BUSINESS (5) ---
    (
        "Just opened a coffee shop on McCulloch — address 400 McCulloch, phone 928-555-0100, hours 6am-2pm.",
        "contribute",
        "NEW_BUSINESS",
    ),
    (
        "Adding a new retail storefront — we are open 10-6, call us at 928-555-1212, located at 12 Main St.",
        "contribute",
        "NEW_BUSINESS",
    ),
    ("New business: corner of Jamaica and Swanson, suite 3, phone 928-555-9999.", "contribute", "NEW_BUSINESS"),
    ("Just opened — hours weekdays 9-5, address 200 Lake Havasu Ave.", "contribute", "NEW_BUSINESS"),
    ("Put in a new shop with storefront on London Bridge Rd, phone on file 928-555-4141.", "contribute", "NEW_BUSINESS"),
    # --- contribute: NEW_PROGRAM (5) ---
    (
        "Adding weekly gymnastics classes for ages 6 to 12 with enrollment on Mondays.",
        "contribute",
        "NEW_PROGRAM",
    ),
    (
        "New program: swim lessons every Tuesday, sign up for sessions every week.",
        "contribute",
        "NEW_PROGRAM",
    ),
    (
        "I want to add a class schedule for toddlers — lessons every Thursday morning.",
        "contribute",
        "NEW_EVENT",
    ),
    ("Adding karate instruction — program runs year-round, age group 8-14.", "contribute", "NEW_PROGRAM"),
    ("New youth program with weekly sessions and enrollment forms at the desk.", "contribute", "NEW_PROGRAM"),
    # --- correct: CORRECTION (10) ---
    ("That is wrong — the phone changed.", "correct", "CORRECTION"),
    ("Actually it's on Kiowa now, not McCulloch.", "correct", "CORRECTION"),
    ("The address moved to 50 Acoma Blvd.", "correct", "CORRECTION"),
    ("That's incorrect, the hours are now 9 to 5.", "correct", "CORRECTION"),
    ("Used to be at Sara Park but it relocated to the mall.", "correct", "CORRECTION"),
    ("You have the wrong time listed for the fireworks.", "correct", "CORRECTION"),
    ("The phone is actually 928-555-7777.", "correct", "CORRECTION"),
    ("Isn't at London Bridge Rd anymore — now it's on Jamaica.", "correct", "CORRECTION"),
    ("Changed to Saturday at 7pm, not Friday.", "correct", "CORRECTION"),
    ("Now it's closed on Mondays — update that.", "correct", "CORRECTION"),
    # --- chat: GREETING (5) ---
    ("Hi", "chat", "GREETING"),
    ("Hey there", "chat", "GREETING"),
    ("Hello", "chat", "GREETING"),
    ("Good morning", "chat", "GREETING"),
    ("What is up", "chat", "GREETING"),
    # --- chat: OUT_OF_SCOPE (5) ---
    ("What is the weather this weekend?", "chat", "OUT_OF_SCOPE"),
    ("Best restaurant for tacos?", "chat", "OUT_OF_SCOPE"),
    ("Where should I buy a house in Havasu?", "chat", "OUT_OF_SCOPE"),
    ("Is it going to rain tomorrow?", "chat", "OUT_OF_SCOPE"),
    ("Hotel recommendations near the lake?", "chat", "OUT_OF_SCOPE"),
    # --- chat: SMALL_TALK (5) ---
    ("Thanks", "chat", "SMALL_TALK"),
    ("Thank you!", "chat", "SMALL_TALK"),
    ("How are you?", "chat", "SMALL_TALK"),
    ("Bye", "chat", "SMALL_TALK"),
    ("Appreciate it.", "chat", "SMALL_TALK"),
]


@pytest.mark.parametrize("query,expected_mode,expected_sub", _CLASSIFY_FIXTURES)
def test_classify_modes_and_sub_intents(query: str, expected_mode: str, expected_sub: str) -> None:
    result: IntentResult = classify(query)
    assert result.mode == expected_mode, f"{query!r}: got mode {result.mode}"
    assert result.sub_intent == expected_sub, f"{query!r}: got sub_intent {result.sub_intent}"


def test_classify_fixture_count() -> None:
    assert len(_CLASSIFY_FIXTURES) >= 80


def test_intent_result_includes_raw_and_normalized() -> None:
    r = classify("  What's the WEBSITE for Altitude?  ")
    assert r.raw_query == "What's the WEBSITE for Altitude?"
    assert "website" in r.normalized_query
    assert r.mode == "ask"


def test_entity_hint_when_provider_alias_present() -> None:
    r = classify("What time does bmx start Saturday?")
    assert r.mode == "ask"
    assert r.entity == "Lake Havasu City BMX"


def test_confidence_is_fraction() -> None:
    r = classify("Where is altitude?")
    assert 0.0 <= r.confidence <= 1.0
