# Havasu Chat — User Query Test Battery

> **Purpose:** A comprehensive, realistic set of queries that real users might send to the app. Each entry specifies what the CORRECT response category is, so Claude Code can run the battery, compare actual vs expected, and flag bugs systematically.
>
> **How to use:** Claude Code hits each query against production /chat and classifies the response into one of the four categories below. Any mismatch between expected and actual is a bug.

---

## Response Categories

Every query resolves to exactly one of these:

- **EVENTS** — app returns one or more real events matching the query
- **NO_MATCH** — app returns honest no-match copy ("nothing on for that time" or similar)
- **VENUE_REDIRECT** — app returns the venue-recognized response naming the venue
- **OUT_OF_SCOPE** — app returns category-specific redirect (weather, lodging, transportation, dining directory, commercial services / rentals)

---

## Instructions for Claude Code

For each query below, do the following:

1. Hit the production /chat endpoint with the exact query text and an empty session state.
2. Classify the response into one of the four categories above.
3. Capture the intent, date_range, and count returned.
4. Flag any mismatch between the Expected category and the Actual category as a BUG.
5. Report results in a summary table with columns: Query, Expected, Actual, Match (YES/NO/BUG), Notes.

At the end, produce a bug list sorted by severity:
- **Severity 1** — query returns unrelated events (wrong EVENTS instead of NO_MATCH)
- **Severity 2** — query returns NO_MATCH when it should return EVENTS
- **Severity 3** — query returns NO_MATCH when it should return VENUE_REDIRECT
- **Severity 4** — wrong OUT_OF_SCOPE category or missed OUT_OF_SCOPE detection
- **Severity 5** — correct category but unexpected date range or other minor issue

Do not fix anything yet. Produce the report first.

---

## 1. Real Events That Should Match (EVENTS expected)

These should all return at least one real event. If any return NO_MATCH, that is a Severity 2 bug.

| # | Query | Expected | Reason |
|---|---|---|---|
| 1 | boat race | EVENTS | Desert Storm Poker Run is seeded |
| 2 | poker run | EVENTS | Same event |
| 3 | regatta | EVENTS | Synonym for boat race |
| 4 | live music | EVENTS | Multiple concert events seeded |
| 5 | concert | EVENTS | Same |
| 6 | band | EVENTS | Concert synonym |
| 7 | kids activities | EVENTS | Family events seeded |
| 8 | family fun | EVENTS | Same |
| 9 | things to do | EVENTS | Broad listing query |
| 10 | whats happening | EVENTS | Broad listing query |
| 11 | things to do next month | EVENTS | Seed data has June/July events |
| 12 | events in may | EVENTS | Seed data has May events |
| 13 | events in june | EVENTS | Seed data has June events |
| 14 | events in july | EVENTS | Seed data has July events |
| 15 | farmers market | EVENTS | Recurring market is seeded |
| 16 | sunset market | EVENTS | Havasu Sunset Market is seeded |
| 17 | first friday | EVENTS | Downtown First Friday is seeded (query must not be treated as “next Friday” date-only) |
| 18 | fireworks | EVENTS | July 4 / fireworks celebration seeded |
| 19 | 4th of july | EVENTS | Same |
| 20 | country music | EVENTS | Concert events are seeded |

---

## 2. Specific Nouns With No Matching Event (NO_MATCH expected)

These name a real activity type but have no matching events currently seeded. They must trigger honest no-match, not return random events. Any EVENTS result here is a Severity 1 bug.

| # | Query | Expected | Reason |
|---|---|---|---|
| 21 | trampoline | NO_MATCH or VENUE_REDIRECT | Altitude is a venue, not an event |
| 22 | trampoline tonight | NO_MATCH | No trampoline events |
| 23 | bowling | NO_MATCH or VENUE_REDIRECT | Havasu Lanes is a venue |
| 24 | bowling this week | NO_MATCH or VENUE_REDIRECT | Same |
| 25 | rodeo | NO_MATCH | No rodeo events seeded |
| 26 | comedy show | NO_MATCH | No comedy seeded |
| 27 | karaoke | NO_MATCH | No karaoke seeded |
| 28 | trivia night | NO_MATCH | No trivia seeded |
| 29 | wine tasting | NO_MATCH | None seeded |
| 30 | brewery tour | NO_MATCH | None seeded |
| 31 | paint night | NO_MATCH | None seeded |
| 32 | book club | NO_MATCH | None seeded |
| 33 | tennis tournament | NO_MATCH | None seeded |
| 34 | pickleball | EVENTS | Pickleball open play is seeded |
| 35 | 5k run | NO_MATCH | None seeded |
| 36 | marathon | NO_MATCH | None seeded |
| 37 | bingo | NO_MATCH | None seeded |
| 38 | poetry reading | NO_MATCH | None seeded |
| 39 | film screening | NO_MATCH | None seeded |
| 40 | dog show | NO_MATCH | None seeded |

---

## 3. Known Venues (VENUE_REDIRECT expected)

These name real Lake Havasu venues. They should trigger the venue redirect copy. Plain NO_MATCH here is acceptable but VENUE_REDIRECT is the preferred behavior (Severity 3 if NO_MATCH fires instead of VENUE_REDIRECT, Severity 1 if unrelated events fire).

| # | Query | Expected | Reason |
|---|---|---|---|
| 41 | altitude trampoline park | VENUE_REDIRECT | Real venue in registry |
| 42 | havasu lanes | VENUE_REDIRECT | Real venue in registry |
| 43 | sara park | VENUE_REDIRECT | Real park in registry |
| 44 | london bridge | VENUE_REDIRECT | Landmark in registry |
| 45 | rotary park | VENUE_REDIRECT | Real park |
| 46 | lake havasu state park | VENUE_REDIRECT | Real park |
| 47 | cattail cove | VENUE_REDIRECT | Real park |
| 48 | english village | VENUE_REDIRECT | Real landmark |
| 49 | aquatic center | VENUE_REDIRECT | Real venue |
| 50 | scooter's | VENUE_REDIRECT | Real family fun center |
| 51 | bridgewater links | VENUE_REDIRECT | Real golf course |
| 52 | copper still distillery | VENUE_REDIRECT | Real distillery |

---

## 4. Out-of-Scope Queries (OUT_OF_SCOPE expected)

These should hit the OUT_OF_SCOPE intent from Session L. Any EVENTS or NO_MATCH result is a Severity 4 bug.

**Weather category:**
| # | Query | Expected |
|---|---|---|
| 53 | whats the weather | OUT_OF_SCOPE (weather) |
| 54 | weather this weekend | OUT_OF_SCOPE (weather) |
| 55 | is it going to rain | OUT_OF_SCOPE (weather) |
| 56 | how hot is it | OUT_OF_SCOPE (weather) |
| 57 | temperature today | OUT_OF_SCOPE (weather) |
| 58 | forecast | OUT_OF_SCOPE (weather) |

**Lodging category:**
| # | Query | Expected |
|---|---|---|
| 59 | where should i stay | OUT_OF_SCOPE (lodging) |
| 60 | hotels in havasu | OUT_OF_SCOPE (lodging) |
| 61 | best motel | OUT_OF_SCOPE (lodging) |
| 62 | airbnb near me | OUT_OF_SCOPE (lodging) |
| 63 | place to sleep | OUT_OF_SCOPE (lodging) |

**Transportation / directions category:**
| # | Query | Expected |
|---|---|---|
| 64 | where do i park | OUT_OF_SCOPE (transportation) |
| 65 | parking downtown | OUT_OF_SCOPE (transportation) |
| 66 | directions to london bridge | OUT_OF_SCOPE (transportation) |
| 67 | how far is phoenix | OUT_OF_SCOPE (transportation) |
| 68 | is there uber here | OUT_OF_SCOPE (transportation) |
| 69 | rent a car | OUT_OF_SCOPE (transportation) |

**Dining directory category:**
| # | Query | Expected |
|---|---|---|
| 70 | best restaurants | OUT_OF_SCOPE (dining) |
| 71 | top restaurants in havasu | OUT_OF_SCOPE (dining) |
| 72 | where to eat | OUT_OF_SCOPE (dining) |
| 73 | best breakfast | OUT_OF_SCOPE (dining) |

---

## 5. Event-Indicator Overrides (EVENTS or NO_MATCH expected, NOT OUT_OF_SCOPE)

These contain words that would normally trigger OUT_OF_SCOPE but also contain strong event indicators. The event indicator must win. Any OUT_OF_SCOPE result here is a Severity 4 bug.

| # | Query | Expected | Why |
|---|---|---|---|
| 74 | hotel grand opening event | EVENTS or NO_MATCH | "event" overrides "hotel" |
| 75 | restaurant week | EVENTS or NO_MATCH | "week" overrides "restaurant" |
| 76 | food festival | EVENTS or NO_MATCH | "festival" overrides "food" |
| 77 | car show | EVENTS or NO_MATCH | Not an auto directory query |
| 78 | weather station tour | EVENTS or NO_MATCH | "tour" should override |

---

## 6. Date Phrase Parsing (EVENTS or NO_MATCH with correct date range)

These test whether date phrases are parsed correctly. The category is less important than whether the returned date_range matches expectations. Severity 5 for wrong date range, Severity 1 if unrelated events appear.

| # | Query | Expected date_range | Notes |
|---|---|---|---|
| 79 | events today | today only | |
| 80 | events tonight | today only | |
| 81 | events tomorrow | tomorrow only | |
| 82 | this week | today through end of week | Session P should cover this |
| 83 | this weekend | upcoming Sat-Sun | |
| 84 | next weekend | weekend after | |
| 85 | this month | today through end of month | Session P |
| 86 | next month | first-last of next month | Session P |
| 87 | in may | full month of May | |
| 88 | memorial day | May holiday | |
| 89 | july 4 | July 4 specifically | |

---

## 7. Session State Multi-Turn Tests

These require running a sequence of queries in one session. Session N fixed the carryover bug — verify it holds.

**Sequence A — broad after narrow:**
| # | Query | Expected | Session state check |
|---|---|---|---|
| 90 | this weekend | NO_MATCH (no weekend events) | date_range = upcoming weekend |
| 91 | any boat events | EVENTS | date_range must be CLEARED |
| 92 | what about next week | NO_MATCH or EVENTS | date_range = next week |

**Sequence B — date phrase overrides:**
| # | Query | Expected | Session state check |
|---|---|---|---|
| 93 | whats happening this weekend | NO_MATCH | date_range = weekend |
| 94 | concerts in july | EVENTS | date_range = July, NOT still weekend |

**Sequence C — week-after advancement:**
| # | Query | Expected | Session state check |
|---|---|---|---|
| 95 | this weekend | NO_MATCH | date_range = April 18-19 |
| 96 | the week after that | NO_MATCH | date_range = April 25-May 1 |
| 97 | how about the week after | NO_MATCH | date_range = May 2-8 |

---

## 8. Edge Cases and Potential Traps

| # | Query | Expected | Notes |
|---|---|---|---|
| 98 | "" (empty string) | Some graceful response | Should not crash |
| 99 | a | Some graceful response | Single character |
| 100 | !@#$%^ | Some graceful response | Symbols only |
| 101 | bowling alley near me | VENUE_REDIRECT or NO_MATCH | "near me" is a location hint |
| 102 | cheap boat rental | OUT_OF_SCOPE (commercial_services) | Rentals / services, not calendar events |
| 103 | is there parking at the festival | OUT_OF_SCOPE (transportation) wins, OR EVENTS for festival | Ambiguous |
| 104 | kids birthday party venue | OUT_OF_SCOPE (commercial_services) or VENUE_REDIRECT | Venue shopping, not event discovery |
| 105 | date night ideas | EVENTS | Broad romantic listing |
| 106 | romantic things to do | EVENTS | Same |
| 107 | senior activities | EVENTS | Demographic |
| 108 | dog friendly events | EVENTS or NO_MATCH | Pet filter |
| 109 | free events | EVENTS | Cost filter |
| 110 | indoor activities when its hot | EVENTS or NO_MATCH | Weather-adjacent but event-focused |

---

## 9. Adversarial and Ambiguous Queries

| # | Query | Expected | Notes |
|---|---|---|---|
| 111 | add an event | ADD_EVENT flow | Not search |
| 112 | help | Greeting / help response | Meta query |
| 113 | what can you do | Capabilities response | Meta |
| 114 | hi | Greeting | |
| 115 | thanks | Graceful acknowledgment | |
| 116 | i love this app | Graceful response | |
| 117 | this is broken | Graceful response | |
| 118 | tell me a joke | OUT_OF_SCOPE or graceful decline | Not events |
| 119 | book me a table | NO_MATCH or OUT_OF_SCOPE | Reservation, not event |
| 120 | buy tickets to the concert | EVENTS or OUT_OF_SCOPE | App doesn't sell tickets |

---

## 10. Submission Report Format

After running all 120 queries, produce this structure:

### Summary stats
- Total queries: 120
- Correct responses: X
- Bugs found: Y
- Pass rate: Z%

### Severity 1 bugs (wrong events shown)
List each with query, expected category, actual response.

### Severity 2 bugs (missed events)
Same format.

### Severity 3 bugs (missed venue redirect)
Same format.

### Severity 4 bugs (OUT_OF_SCOPE issues)
Same format.

### Severity 5 bugs (date range or minor issues)
Same format.

### Recommendations
Based on the bug patterns, which code area needs the next fix — search.py, slots.py, intent.py, venues.py, or conversation_copy.py? Do NOT propose code fixes, just identify the problem area.

---

## 11. Execution Constraints

- Do not run any code changes during this session. This is purely a test battery run.
- Use a fresh session for each query to avoid session state contamination, except for the multi-turn sequences in Section 7.
- If a query takes more than 10 seconds to respond, flag it as a potential timeout bug.
- If the app crashes or returns 500 on any query, that is a Severity 1 bug — show the full error.
- Complete the full battery before summarizing. Do not stop early.

---

## 12. After the Battery

Based on the bug report, we will decide whether the next session should:
- Fix search ranking issues
- Fix intent routing
- Expand the venue registry
- Expand the synonym dictionary
- Tighten the OUT_OF_SCOPE overrides
- Do something else entirely

The goal of this battery is to expose the highest-value fix before guessing..: 