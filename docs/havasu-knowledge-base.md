# Havasu Chat — Query Knowledge Base
> **Purpose:** Canonical reference for what users ask about in Lake Havasu City and how the app should answer. Feeds into `_SPECIFIC_PHRASES` in `search.py`, `QUERY_SYNONYMS` in `slots.py`, and product-level response strategy decisions.
>
> **Audience:** Solo dev (Casey) and any AI coding assistant making changes to search behavior.

---

## 1. The Core Decision Framework
Before tuning queries, understand the three response types the app can produce. Every query should resolve to exactly one of these.

**A. Event match.** The app has one or more real events that match the query. Show them ranked by relevance and date. Example: user asks "boat race" → show Desert Storm Poker Run.

**B. Honest no-match.** The query names a specific thing the app tracks, but no events currently match. Say so directly without substituting loosely related events. Example: "trampoline tonight" → "I don't have any trampoline events scheduled right now."

**C. Venue / business redirect.** The query names a permanent local business (not a dated event). Havasu Chat is an events app, not a directory, so the right answer is to acknowledge the venue and explain what the app actually covers. Example: "Altitude Trampoline Park hours" → "Altitude Trampoline Park is open daily in Lake Havasu. I track dated events like parties and tournaments there — nothing currently listed, but I can let you know if something comes up."

The "trampoline" bug from production (Sky Lantern Festival returned for a trampoline query) is type A wrongly fired when the right answer was type B or C.

---

## 2. Fundamental Product Questions to Settle
Before adding 100 new specific phrases, answer these. The answers dictate the code changes.

**Q1. When a user searches for a venue (trampoline park, bowling alley, aquatic center), should the app:**
- (a) Return honest no-match because the app only tracks dated events, or
- (b) Treat major venues as persistent "always-available" entries and return them, or
- (c) Return honest no-match plus a one-line suggestion ("This is an events app. Altitude Trampoline Park is open daily — search their website for hours.")

Recommended: (c). It's honest, useful, and doesn't bloat the database with non-events.

**Q2. What is the app's geographic scope?**
- Just Lake Havasu City proper?
- Include nearby destinations (Parker Dam, Oatman, Bullhead City)?

Recommended: Lake Havasu City only. Users can ask elsewhere for regional trips.

**Q3. Does the app answer trip-planning questions ("what should I do this weekend") differently from specific-event queries ("boat race")?**

Recommended: Yes. Trip-planning queries use the general 0.35 threshold and return 5-9 diverse events. Specific-event queries use the 0.55 threshold with literal-match required.

---

## 3. Query Categories (What Users Actually Ask About)
This section maps the universe of likely queries to category buckets. Each category lists:
- **Typical phrasings** (what users type)
- **Specific nouns** (the exact words that should trigger high-threshold matching)
- **Synonyms** (what these words mean, for query expansion)
- **Response strategy** (A, B, or C from Section 1)

### 3.1 Water Activities — The Core of Havasu
Havasu is a water destination first. Expect these to be high-volume queries.

**Boating / powerboats**
- Typical: "boat rental," "go boating," "rent a boat," "powerboat"
- Specific nouns: boat, boating, powerboat, pontoon, speedboat, yacht
- Synonyms: boat → powerboat, pontoon, cruiser, watercraft
- Response: Mostly type C (rentals are businesses, not events). Type A only for boat shows, poker runs, or organized cruises.

**Jet skis / personal watercraft**
- Typical: "jet ski," "wave runner," "rent jet skis"
- Specific nouns: jet ski, jetski, waverunner, wave runner, PWC, seadoo
- Synonyms: jet ski → waverunner, pwc, seadoo, personal watercraft
- Response: Type C for rentals; type A for jet ski races or poker runs.

**Kayaking, paddleboarding, canoeing**
- Typical: "kayak rental," "paddleboard," "SUP," "canoe the bridge"
- Specific nouns: kayak, kayaking, paddleboard, SUP, canoe, paddle
- Synonyms: paddleboard → SUP, stand up paddle; kayak → canoe, paddle
- Response: Type C for rentals; type A for organized paddle events.

**Boat races / poker runs / regattas**
- Typical: "boat race," "poker run," "regatta," "Desert Storm," "speedboat race"
- Specific nouns: boat race, regatta, poker run, speedboat race, boat racing
- Synonyms: boat race → regatta, poker run, boat racing, desert storm
- Response: Type A. Already working well post-Session A.

**Boat tours**
- Typical: "boat tour," "lake tour," "jet boat tour," "sunset cruise," "Topock Gorge tour," "lighthouse tour"
- Specific nouns: boat tour, jet boat, sunset cruise, Topock, gorge tour
- Synonyms: boat tour → cruise, lake tour, sightseeing cruise
- Response: Type C for daily tours; type A for special charters.

**Fishing**
- Typical: "fishing," "fishing tournament," "bass fishing," "where to fish"
- Specific nouns: fishing, fishing tournament, bass tournament, fishing derby
- Synonyms: fishing → angling, bass fishing; tournament → derby, competition
- Response: Type A for tournaments; type C for general fishing info.

**Swimming / beach**
- Typical: "beach," "swimming," "where to swim," "London Bridge Beach," "Rotary Park"
- Specific nouns: beach, swim, swimming, London Bridge Beach, Rotary Park
- Synonyms: beach → shoreline, swim area; swim → swimming, water
- Response: Type C for beach access info; type A for beach events (movie nights, bonfires).

### 3.2 Land Activities

**Hiking**
- Typical: "hiking trails," "where to hike," "SARA Park," "Crack in the Mountain"
- Specific nouns: hiking, hike, trail, trails, SARA Park, Crack in the Mountain
- Synonyms: hike → trail, walk, trek; hiking → trail walking
- Response: Type C mostly (trails are permanent); type A for group hikes.

**Mountain biking**
- Typical: "mountain bike," "MTB trails," "bike trail"
- Specific nouns: mountain bike, MTB, bike trail, biking
- Synonyms: mountain biking → MTB, cycling, bike riding
- Response: Type C; type A for bike races or group rides.

**Off-roading / ATV / UTV**
- Typical: "off-road," "ATV rental," "UTV tour," "dune buggy," "side by side"
- Specific nouns: ATV, UTV, off road, off-road, dune, side by side, 4x4
- Synonyms: off-road → ATV, UTV, 4x4, side by side, jeep tour
- Response: Type C for rentals; type A for organized off-road events.

**Golf**
- Typical: "golf," "golf course," "tee time," "Bridgewater Links"
- Specific nouns: golf, golf course, tee time, Bridgewater Links
- Synonyms: golf → tee off, golf course, links
- Response: Type C for tee times; type A for golf tournaments.

**Hot air balloon**
- Typical: "balloon ride," "hot air balloon," "balloon festival"
- Specific nouns: balloon, hot air balloon, balloon ride, balloon festival
- Synonyms: balloon → hot air balloon, balloon ride
- Response: Type C for rides; type A for the annual Balloon Festival.

### 3.3 Sightseeing & Landmarks

**London Bridge**
- Typical: "London Bridge," "the bridge," "see the bridge"
- Specific nouns: London Bridge, the bridge, bridge tour
- Synonyms: London Bridge → the bridge, historic bridge
- Response: Type C (permanent landmark); type A for bridge-related events.

**Lighthouses**
- Typical: "lighthouses," "lighthouse tour," "see the lighthouses"
- Specific nouns: lighthouse, lighthouses
- Synonyms: lighthouse → replica lighthouse, lighthouse tour
- Response: Type C; type A for lighthouse tours.

**English Village**
- Typical: "English Village," "shops by the bridge," "shopping downtown"
- Specific nouns: English Village, downtown shops
- Synonyms: English Village → shops, boutiques, downtown
- Response: Type C; type A for village events.

**Museums / history**
- Typical: "museum," "history," "Lake Havasu Museum of History"
- Specific nouns: museum, history museum
- Synonyms: museum → history, exhibit
- Response: Type C; type A for special exhibits.

### 3.4 Family / Kids Activities
This is the category where the "trampoline" bug happened. Lots of specific venue names here.

**Trampoline park**
- Typical: "trampoline," "trampoline park," "Altitude," "jumping"
- Specific nouns: trampoline, trampoline park, Altitude
- Synonyms: trampoline → jumping, Altitude, trampoline park
- Response: Type C (Altitude is a permanent business); type A for parties/events there.

**Bowling**
- Typical: "bowling," "bowl," "Havasu Lanes," "cosmic bowling"
- Specific nouns: bowling, bowl, Havasu Lanes, cosmic bowling
- Synonyms: bowling → bowl, Havasu Lanes
- Response: Type C; type A for bowling tournaments or cosmic bowling nights.

**Arcade / family fun**
- Typical: "arcade," "Scooter's," "family fun center," "mini golf"
- Specific nouns: arcade, mini golf, Scooter's, family fun
- Synonyms: arcade → video games, fun center; mini golf → putt putt
- Response: Type C; type A for arcade events.

**Aquatic Center / pool**
- Typical: "swimming pool," "aquatic center," "public pool," "pool party"
- Specific nouns: aquatic center, pool, swimming pool
- Synonyms: pool → swimming, aquatic center
- Response: Type C for open swim; type A for pool events (dive-in movies, swim meets).

**Playgrounds / parks for kids**
- Typical: "playground," "park for kids," "Rotary Park"
- Specific nouns: playground, park, Rotary Park
- Synonyms: playground → park, kids play area
- Response: Type C; type A for park events.

**Indoor play**
- Typical: "indoor play," "Sunshine Indoor Play," "indoor kids"
- Specific nouns: indoor play, Sunshine Indoor Play
- Synonyms: indoor play → indoor kids, play center
- Response: Type C.

**General kids / family**
- Typical: "kids activities," "family fun," "something for kids," "things to do with kids"
- Specific nouns: none — this is a general category query
- Synonyms: kids → children, family, family-friendly
- Response: Type A. Show a diverse list of family events from existing data. Currently working.

### 3.5 Dining, Drinks, Nightlife

**Restaurants / dining**
- Typical: "restaurants," "dinner," "breakfast," "brunch," "lunch"
- Specific nouns: restaurant, dinner, breakfast, brunch, lunch
- Synonyms: dining → eat, food, restaurant
- Response: Type C for restaurants; type A for food events (restaurant weeks, tastings, pop-ups).

**Bars / happy hour**
- Typical: "bars," "happy hour," "drinks," "cocktails"
- Specific nouns: bar, happy hour, cocktails
- Synonyms: bar → pub, lounge, tavern; drinks → cocktails, booze
- Response: Type C; type A for bar events (trivia nights, special tastings).

**Breweries / distilleries**
- Typical: "brewery," "beer," "distillery," "Copper Still," "Hava Bite"
- Specific nouns: brewery, distillery, Copper Still, Hava Bite, taproom
- Synonyms: brewery → beer, ale, craft beer, taproom
- Response: Type C; type A for tastings, releases, brewery events.

**Live music / concerts**
- Typical: "live music," "concert," "band tonight," "DJ"
- Specific nouns: concert, live music, band, DJ, show
- Synonyms: live music → concert, band, DJ, performance, show
- Response: Type A. Already working well.

**Dance clubs / nightlife**
- Typical: "nightlife," "dance," "club," "DJ night"
- Specific nouns: club, dance club, nightlife
- Synonyms: nightclub → dance club, bar with dancing
- Response: Type A for dance events; type C for general nightlife.

**Food trucks / markets**
- Typical: "food trucks," "farmers market," "sunset market," "street food"
- Specific nouns: food truck, farmers market, sunset market
- Synonyms: farmers market → market, sunset market; food truck → food cart
- Response: Type A. Recurring events.

### 3.6 Events & Entertainment

**Festivals**
- Typical: "festival," "Balloon Festival," "Winterfest," "Bluewater"
- Specific nouns: festival, Balloon Festival, Winterfest, Bluewater, Sky Lantern
- Synonyms: festival → fest, celebration
- Response: Type A.

**Parades**
- Typical: "parade," "holiday parade," "Christmas parade," "boat parade"
- Specific nouns: parade, boat parade
- Synonyms: parade → procession, march
- Response: Type A.

**Fireworks**
- Typical: "fireworks," "4th of July fireworks," "NYE fireworks"
- Specific nouns: fireworks, fireworks show
- Synonyms: fireworks → firework show, pyrotechnics
- Response: Type A. Tied to specific dates.

**Holiday / seasonal**
- Typical: "4th of July," "Halloween," "Christmas," "New Year's Eve," "Easter"
- Specific nouns: (holiday names themselves act as date filters)
- Synonyms: 4th of July → Fourth, Independence Day; NYE → New Year's Eve
- Response: Type A filtered by date.

**Car / motorcycle shows**
- Typical: "car show," "motorcycle," "bike night," "Rockabilly Reunion"
- Specific nouns: car show, motorcycle, bike night, auto show
- Synonyms: car show → auto show, classic car; motorcycle → bike, motorbike
- Response: Type A.

### 3.7 Wellness & Classes

**Yoga / fitness / classes**
- Typical: "yoga," "fitness class," "workout," "pilates"
- Specific nouns: yoga, fitness, pilates, workout, class
- Synonyms: yoga → stretching; fitness → workout, exercise, gym class
- Response: Type A for scheduled classes.

**Spa / massage**
- Typical: "spa," "massage," "wellness"
- Specific nouns: spa, massage
- Synonyms: spa → wellness, massage
- Response: Type C mostly.

### 3.8 Practical / Logistics Queries

**Weather / what to bring**
- Typical: "is it hot," "weather," "what to wear"
- Response: Out of scope. Return "I'm an events app — I don't do weather. Try weather.com."

**Getting there / parking**
- Typical: "parking," "how to get there," "directions"
- Response: Out of scope. Return "I track events, not logistics. Event details include a location you can map."

**Hotels / lodging**
- Typical: "hotel," "where to stay," "Airbnb"
- Response: Out of scope. "I track events, not lodging. Check VisitArizona or Airbnb."

### 3.9 Meta Queries

**App capability questions**
- Typical: "what can you do," "help," "how does this work"
- Response: Friendly capabilities explanation. Already handled by onboarding chips.

**Submit an event**
- Typical: "add an event," "post an event," "submit"
- Response: Trigger the ADD_EVENT intent flow. Already working.

---

## 4. Specific Phrases — Recommended Additions to `_SPECIFIC_PHRASES`
Current code in `search.py` has a limited tuple. Expand it with these, organized by category so future additions are easy to slot in.

```python
_SPECIFIC_PHRASES = (
    # Water sports & races
    "boat race", "boat racing", "regatta", "poker run", "speedboat race",
    "desert storm", "jet ski", "jetski", "waverunner", "kayak", "paddleboard",
    "SUP", "canoe", "jet boat", "boat tour", "sunset cruise", "fishing tournament",
    # Beaches & parks
    "london bridge beach", "rotary park", "lake havasu state park",
    "cattail cove", "sara park",
    # Land activities
    "hiking", "mountain bike", "MTB", "ATV", "UTV", "off-road", "dune",
    "golf tournament", "tee time", "balloon ride", "balloon festival",
    # Sightseeing
    "london bridge", "lighthouse", "english village", "museum",
    # Family / kids venues
    "trampoline", "trampoline park", "altitude", "bowling", "havasu lanes",
    "cosmic bowling", "arcade", "mini golf", "scooter's", "aquatic center",
    "swimming pool", "playground", "sunshine indoor play",
    # Dining & drinks
    "happy hour", "brewery", "distillery", "copper still", "hava bite",
    "taproom", "food truck", "farmers market", "sunset market",
    # Entertainment
    "concert", "live music", "band", "DJ", "dance", "karaoke",
    "festival", "parade", "fireworks", "car show", "motorcycle",
    "bike night", "rockabilly",
    # Wellness
    "yoga", "pilates", "fitness class", "spa",
)
```

---

## 5. Synonym Dictionary — Recommended Additions to `QUERY_SYNONYMS`

```python
QUERY_SYNONYMS = {
    # Water
    "boat race": ["regatta", "poker run", "boat racing", "speedboat race", "desert storm"],
    "jet ski": ["waverunner", "wave runner", "pwc", "personal watercraft", "seadoo"],
    "kayak": ["canoe", "paddle", "paddling"],
    "paddleboard": ["SUP", "stand up paddle", "paddleboarding"],
    "boat tour": ["cruise", "lake tour", "sightseeing boat", "jet boat tour"],
    "fishing": ["angling", "bass fishing", "fishing tournament", "fishing derby"],
    # Land
    "hiking": ["hike", "trail", "trek", "trail walking"],
    "off-road": ["ATV", "UTV", "4x4", "side by side", "jeep tour", "dune"],
    "mountain bike": ["MTB", "bike trail", "cycling"],
    "golf": ["tee off", "golf course", "links", "tee time"],
    "balloon": ["hot air balloon", "balloon ride", "balloon festival"],
    # Family / kids
    "trampoline": ["trampoline park", "jumping", "altitude"],
    "bowling": ["bowl", "havasu lanes", "cosmic bowling"],
    "arcade": ["video games", "fun center", "scooter's"],
    "mini golf": ["putt putt", "miniature golf"],
    "kids": ["children", "family", "family-friendly", "toddler"],
    "aquatic center": ["pool", "swimming pool", "public pool"],
    # Dining & drinks
    "restaurant": ["dining", "eat", "food", "dinner"],
    "bar": ["pub", "lounge", "tavern", "drinks"],
    "happy hour": ["drinks special", "discount drinks"],
    "brewery": ["beer", "ale", "craft beer", "taproom"],
    "farmers market": ["market", "sunset market", "local market"],
    "food truck": ["food cart", "street food"],
    # Entertainment
    "concert": ["live music", "band", "show", "performance", "DJ"],
    "festival": ["fest", "celebration"],
    "parade": ["procession", "march", "boat parade"],
    "fireworks": ["firework show", "pyrotechnics"],
    "car show": ["auto show", "classic car", "car meet"],
    "motorcycle": ["bike", "motorbike", "bike night"],
    # Wellness
    "yoga": ["stretching", "mindfulness class"],
    "fitness": ["workout", "exercise", "gym class", "pilates"],
}
```

---

## 6. Venue Registry — Real Places Users Will Name
These are real businesses and landmarks in Lake Havasu. When a user names one, the app should recognize it even if no current event matches. If response strategy C (venue redirect) gets implemented, this becomes the lookup table.

**Family / kids venues**
- Altitude Trampoline Park — 5601 Highway 95 N
- Havasu Lanes — 2128 McCulloch Blvd N (bowling)
- Scooter's Family Fun Center (mini golf, arcade)
- Sunshine Indoor Play
- Lake Havasu Aquatic Center — 100 Park Ave

**Parks & outdoor**
- Lake Havasu State Park
- Cattail Cove State Park
- SARA Park (hiking, mountain biking)
- Rotary Park (beach & playground)
- London Bridge Beach
- Crack in the Mountain Trail

**Water rentals & tours**
- Wet Monkey (boat rentals)
- Havasu Rentals
- Paradise Wild Wave Rentals
- Champion Watercraft Rentals
- Southwest Kayaks
- Cruisin Tikis Havasu
- Sunset Charter & Tour Co
- Bluewater Jet Boat Tours
- Havasu Adventure Company
- Wanderlust Balloons

**Dining / drinks**
- Copper Still Distillery
- Hava Bite Taproom
- Kokomo (bar/nightlife at London Bridge Resort)

**Sightseeing**
- London Bridge
- English Village
- Lake Havasu Museum of History
- 27 replica lighthouses

**Golf**
- Bridgewater Links Golf Course
- London Bridge Resort golf course (9-hole)

---

## 7. Response Copy — What the App Should Actually Say
The response strings below should live in `conversation_copy.py`.

**Honest no-match, specific noun**
"I don't have any [noun] events on the calendar right now. Want me to show you other things happening this week?"

**Venue recognized, no events**
"[Venue] is a permanent spot in Havasu — I track events there when they come up, but nothing is scheduled right now. Want to see what else is happening?"

**Out-of-scope query (weather, hotels, parking)**
"I'm an events app — I stick to what's happening in Havasu rather than [topic]. For [topic], try [golakehavasu.com / weather.com / Airbnb]."

**General listing fallback**
"Here's what's coming up in Havasu:" (followed by top events)

---

## 8. Implementation Plan (Next Sessions)
This knowledge base suggests three separate code sessions, in order of impact:

**Session J — Expand `_SPECIFIC_PHRASES` and `QUERY_SYNONYMS`**
Single-file edits to `search.py` and `slots.py`. Low risk. Adds all the phrases and synonyms in Sections 4 and 5. Expected impact: specific-noun queries (trampoline, bowling, hiking, etc.) correctly trigger honest no-match instead of returning random events.

**Session K — Venue recognition layer (optional, higher-value)**
Add a venue lookup table in `slots.py` or a new file `venues.py`. When a query matches a known venue name, return response type C (acknowledge venue + explain events-only scope). This requires changes to `chat/router.py` to route venue hits separately from event searches.

**Session L — Out-of-scope response handling**
Detect weather, hotel, parking, directions queries and return the out-of-scope copy instead of trying to find events. New intent in `intent.py`: OUT_OF_SCOPE.

---

## 9. Maintenance
This doc should be updated when:
- A new venue opens in Havasu (add to Section 6)
- A new recurring event type launches (add to Section 3)
- A user query returns wrong results in production (root-cause it into the right section)

Keep the `_SPECIFIC_PHRASES` tuple and `QUERY_SYNONYMS` dict in the code as the single source of truth for matching behavior. This document explains *why* those lists are what they are.
