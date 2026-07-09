"""Curated per-leaf SEO copy for the Wave-1 money verticals (Workstream B.2).

Mirrors the ``app/categories/trades.py`` voice: a 40-100 word locally-grounded
intro and 4-6 truthful templated FAQs per leaf. ``{n}`` (live count) and
``{name_lower}`` are filled at render time. No fabricated specifics, no
guaranteed claims — ranking transparency only, matching the site's honesty rules
and DECISION D4 (no AggregateRating; visible star ratings in the cards stay).

Keyed by leaf slug (the ``categories.slug`` for ``level = 1`` rows). A leaf with
no entry here falls back to the generic honest intro in the router.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeafCopy:
    """Curated intro + FAQ pairs for one leaf. ``faqs`` are ``(question,
    answer)`` with ``{n}`` / ``{name_lower}`` placeholders filled at render."""

    intro: str
    faqs: tuple[tuple[str, str], ...]


# The four truthful FAQs every leaf shares (ranking + ratings honesty + how to
# fix a listing). ``{name_lower}`` = the leaf's lowercased display name.
_COMMON_FAQS: tuple[tuple[str, str], ...] = (
    (
        "How many {name_lower} does Ask Hava list in Lake Havasu City?",
        "Ask Hava currently lists {n} {name_lower} serving Lake Havasu City, AZ. "
        "The list comes straight from our local directory and updates as "
        "businesses are added or verified.",
    ),
    (
        "How are these {name_lower} ranked?",
        "The default Featured order rotates the well-reviewed locals daily, so "
        "the same names aren't always on top — both the cutoff and the rotation "
        "pool are based on real public reviews (more reviews, more weight). Tap "
        "Top rated to sort strictly by review strength. Spots can't be bought, "
        "Hava never invents a rating, and any sponsored placement is clearly "
        "labeled.",
    ),
    (
        "Are the ratings and review counts real?",
        "Yes. Star ratings and review counts come from public Google reviews and "
        "show only when a business has a few reviews. Ask Hava never fabricates a "
        "rating.",
    ),
    (
        "How do I add or correct a listing here?",
        "Use the Contribute link in the site footer, or open the business's page "
        "and report wrong info. Local corrections are reviewed before they go "
        "live.",
    ),
)


def _copy(intro: str, *specific: tuple[str, str]) -> LeafCopy:
    """Common four FAQs plus up to two leaf-specific ones (4-6 total)."""
    return LeafCopy(intro=intro, faqs=_COMMON_FAQS + specific[:2])


LEAF_COPY: dict[str, LeafCopy] = {
    "golf-courses": _copy(
        "Golf in Lake Havasu City runs year-round — and it's more than the "
        "courses. The listings below cover public and semi-private golf courses, "
        "the local driving range with Toptracer, and indoor virtual golf "
        "simulators you can play in any weather. Whether you want 18 holes, a "
        "bucket of balls, or a climate-controlled simulator bay, start here. "
        "Listings are ranked by real public reviews; sponsored placements are "
        "always labeled.",
        (
            "What kinds of golf does this page cover?",
            "All of it: full golf courses, the driving range (including Toptracer "
            "range tech), and Lake Havasu's indoor virtual golf simulators — "
            "grouped on one page so you can find the right option fast.",
        ),
        (
            "Can I play golf indoors in Lake Havasu?",
            "Yes — there are indoor virtual golf simulators in town, a popular "
            "way to play or practice out of the summer heat. They're listed here "
            "alongside the outdoor courses and driving range.",
        ),
    ),
    "auto-repair": _copy(
        "Desert heat is hard on cars — batteries cook, coolant systems work "
        "overtime, and AC failures turn a Havasu commute miserable fast. The "
        "auto repair shops below serve Lake Havasu City with everything from "
        "oil changes and brakes to diagnostics, AC work, and major engine and "
        "transmission jobs. Listings are built from real public reviews and "
        "rotate daily, so the shops locals trust stay easy to find.",
        (
            "Why do cars need extra care in Lake Havasu's heat?",
            "Sustained triple-digit summers stress batteries, coolant, and AC "
            "systems well beyond milder climates — many local shops see a summer "
            "spike in heat-related repairs, so preventative checks pay off.",
        ),
    ),
    "general-contractors": _copy(
        "From room additions and kitchen remodels to whole-home builds and "
        "storm repairs, the general contractors below serve Lake Havasu City "
        "and the surrounding area. Desert construction has its own demands — "
        "heat-rated materials, monsoon-ready roofing and drainage, and "
        "energy-efficient cooling — so licensed, reviewed help matters. "
        "Listings are ranked by real public reviews; sponsored "
        "placements are always labeled.",
        (
            "Should a contractor in Arizona be licensed?",
            "For most projects above a small dollar threshold, Arizona requires "
            "a licensed contractor (ROC). Confirm licensing and insurance with "
            "any contractor before work begins — Ask Hava doesn't verify "
            "licenses for you.",
        ),
    ),
    "self-storage": _copy(
        "Boats, RVs, off-season gear, and the overflow from a downsizing move — "
        "Lake Havasu City runs on storage. The self-storage facilities below "
        "offer climate-controlled units, drive-up access, and covered or open "
        "RV and boat parking. Climate control is worth weighing here: summer "
        "heat is brutal on anything sensitive. Listings are ranked by "
        "real public reviews.",
        (
            "Is climate-controlled storage worth it in Havasu?",
            "For electronics, documents, wood furniture, and anything heat- or "
            "humidity-sensitive, many locals choose climate control given the "
            "long, hot summers. For boats, vehicles, and tools, standard or "
            "covered units are common.",
        ),
    ),
    "dentists-and-orthodontists": _copy(
        "Whether it's a routine cleaning, a crown, braces, or an emergency "
        "toothache, the dentists and orthodontists below serve Lake Havasu "
        "City. Many local practices handle general dentistry, cosmetic work, "
        "and orthodontics under one roof, and several see new patients and "
        "families. Listings are built from real public reviews and rotate "
        "daily — never paid placement — so well-reviewed practices stay easy "
        "to find.",
    ),
    "plumbing": _copy(
        "Desert water is hard on pipes — scale buildup, slab leaks, and water "
        "heaters that quit mid-summer. The plumbers below serve Lake Havasu "
        "City, handling drain clearing, re-pipes, fixture installs, water "
        "heaters, and emergency calls. Ratings and review counts come from real "
        "public reviews, so you can see at a glance who locals call back. "
        "Sponsored placements, if any, are clearly labeled.",
        (
            "Do Lake Havasu plumbers handle emergency calls?",
            "Many local plumbing companies offer emergency or same-day service, "
            "but availability varies by company and season — check each "
            "listing's hours and call ahead to confirm.",
        ),
    ),
    "electrical": _copy(
        "From panel upgrades and ceiling fans to RV hookups, boat-dock power, "
        "and EV chargers, the electricians below serve Lake Havasu City homes "
        "and businesses. Desert heat runs AC circuits hard for half the year, "
        "so licensed electrical help matters. Listings are ranked by "
        "real public reviews, and ratings appear only when a "
        "business has earned real reviews.",
    ),
    "roofing": _copy(
        "Havasu roofs take a beating: triple-digit summers, intense UV, and "
        "monsoon winds that find every loose tile. The roofers below handle "
        "repairs, replacements, coatings, and inspections across Lake Havasu "
        "City — tile, shingle, and the foam and flat roofs common on desert "
        "homes. Listings are ranked by real public reviews, never by "
        "who paid; sponsored slots are always labeled.",
        (
            "When is roofing season in Lake Havasu?",
            "Roof work happens year-round, but many locals schedule inspections "
            "before monsoon season (roughly June-September) and book bigger jobs "
            "for the cooler months.",
        ),
    ),
    "real-estate": _copy(
        "Buying a lakefront home, selling a vacation rental, or relocating to "
        "the desert — the real estate professionals below work the Lake Havasu "
        "City market, from the Island and the Channel to the foothills and "
        "outlying communities. Many also handle seasonal and investment "
        "property. Listings are ranked by real public reviews; "
        "Ask Hava doesn't sell ranking and labels any sponsored placement.",
    ),
    "insurance": _copy(
        "Home, auto, boat, RV, and business — the insurance agents below serve "
        "Lake Havasu City. Watercraft and RV coverage matter more here than in "
        "most towns, and desert homes have their own monsoon and sun "
        "considerations. Many local agents write multiple lines and bundle "
        "policies. Listings are ranked by real public reviews, and "
        "ratings show only when a business has earned them.",
    ),
    "financial-advisors": _copy(
        "Retirement planning, investments, and tax-aware strategy — the "
        "financial advisors and planners below serve Lake Havasu City, a town "
        "with a large retiree and second-home population. Whether you're "
        "rolling over a 401(k) or building an income plan, the listings here "
        "draw on real public reviews and rotate daily, keeping well-reviewed "
        "local offices visible. "
        "Ask Hava doesn't sell placement, and isn't a financial adviser itself.",
    ),
    "mortgage-lenders": _copy(
        "Home loans, refinancing, and reverse mortgages — the mortgage lenders "
        "and loan officers below serve Lake Havasu City. With a large retiree "
        "and second-home market, local originators handle everything from "
        "first-time purchases to jumbo and vacation-property financing. Listings "
        "draw on real public reviews and rotate daily, so well-reviewed local "
        "offices stay visible; ratings show only when a lender has earned them. "
        "Ask Hava doesn't sell placement, and isn't a mortgage broker itself.",
    ),
    "hair-salons-and-barbers": _copy(
        "Cuts, color, blowouts, and classic barbering — the hair salons and "
        "barbers below serve Lake Havasu City. From quick walk-in trims to "
        "full-service color and styling, the listings span neighborhood shops "
        "and busier downtown salons. Listings are built from real public "
        "reviews and rotate daily, so the chairs locals book again stay easy "
        "to find; star ratings appear only when a shop has earned real reviews.",
    ),
    "hotels-and-motels": _copy(
        "From channel-side resorts to budget motels and everything between, the "
        "hotels and motels below serve visitors to Lake Havasu City. Rates and "
        "availability swing hard with the seasons — spring break, summer river "
        "weekends, and the Balloon Festival book out fast — so plan ahead for "
        "peak dates. Listings are ranked by real public reviews, "
        "never by who paid.",
        (
            "When is Lake Havasu busiest for lodging?",
            "Spring break, summer river weekends, and big events like the "
            "Balloon Festival drive the highest demand and rates. Mid-week and "
            "the cooler shoulder months are typically calmer and cheaper.",
        ),
    ),
    "vacation-rentals": _copy(
        "Room for the whole crew, a kitchen, and a driveway for the boat "
        "trailer — vacation rentals fill the gap hotels can't, and the ones "
        "below host visitors to Lake Havasu City. From channel-side condos to "
        "desert-view houses with a private pool, short-term rentals book out "
        "earliest for spring break, summer river weekends, and the Balloon "
        "Festival, so reserve ahead for peak dates. Listings are ranked by "
        "real public reviews, never by who paid.",
        (
            "When should I book a Lake Havasu vacation rental?",
            "The larger houses and channel-side units go first for spring "
            "break, summer river weekends, and big events like the Balloon "
            "Festival — often months out. Mid-week and the cooler shoulder "
            "months are easier to book and usually cheaper.",
        ),
        (
            "How is a vacation rental different from a hotel here?",
            "Vacation rentals are whole homes or condos rented by the night or "
            "week — with kitchens, multiple bedrooms, and room to park a boat "
            "or trailer — while hotels and motels offer per-room stays with "
            "daily service. Ask Hava lists both; check each listing's details "
            "and house rules before you book.",
        ),
    ),
    "restaurants": _copy(
        "Lakefront patios, taco joints, steakhouses, and the spots locals "
        "actually drive across town for — the restaurants below serve Lake "
        "Havasu City. Whether you want waterfront dining on the Channel, a "
        "quick bite, or a sit-down dinner, the listings here are built from "
        "real public reviews and rotate daily, so the same kitchens aren't "
        "always on top — tap Top rated to sort by review strength. Hours swing "
        "with the season, so check each listing before you go.",
        (
            "Are there waterfront restaurants in Lake Havasu City?",
            "Yes — several restaurants sit along the Channel and the lakefront. "
            "Use each listing's location and hours to find one near the water, "
            "and call ahead on busy river weekends.",
        ),
    ),
    # Ported from the curated trade pages (app/categories/trades.py) when the
    # trade URLs consolidated onto their taxonomy-leaf twins (SEO PR-B), so
    # the redirect destinations keep the rich local copy.
    "hvac": _copy(
        "When Lake Havasu City hits 115°F, air conditioning isn't a comfort — "
        "it's a necessity. The HVAC companies below install, repair, and "
        "maintain cooling and heating systems across Havasu, from quick "
        "capacitor swaps to full system replacements. Summer is peak season "
        "here, so the smart move is a spring tune-up before the first heat "
        "wave. Ratings shown are from real public reviews.",
        (
            "When should I service my AC in Lake Havasu?",
            "Most local HVAC companies recommend a tune-up in spring, before "
            "summer demand peaks — repair calls back up fast once daily highs "
            "pass 110°F.",
        ),
    ),
    "pools-and-spas": _copy(
        "Backyard pools work overtime in Lake Havasu City — nine-plus months "
        "of swim season means constant chemistry, filtration, and equipment "
        "wear. The pool and spa services below handle weekly cleaning, "
        "green-pool recoveries, pump and filter repairs, and resurfacing "
        "across Havasu. Listings are ranked by real public "
        "reviews; star ratings appear only when a company has earned real "
        "reviews.",
        (
            "How often do Havasu pools need service?",
            "Most local pool companies recommend weekly service in the long "
            "Havasu swim season — heat and sun burn through chlorine far "
            "faster here than in milder climates.",
        ),
    ),
    "pest-control": _copy(
        "Scorpions, ants, roaches, and the occasional pack rat — desert "
        "living comes with desert pests. The pest control companies below "
        "serve Lake Havasu City with one-time treatments, recurring service "
        "plans, and home-sale inspections. Bark scorpions are the local "
        "headline act, so ask about scorpion-specific treatment if that's "
        "your concern. Ratings shown come from real public reviews.",
        (
            "Are scorpions a problem in Lake Havasu City?",
            "Yes — bark scorpions are common across the area, especially in "
            "summer. Most local pest control companies offer "
            "scorpion-specific treatments and recurring plans.",
        ),
    ),
    "landscaping-and-lawn": _copy(
        "Desert landscaping is its own craft — xeriscape design, decorative "
        "rock, drip irrigation, palm trimming, and artificial turf that "
        "survives Havasu summers. The landscapers below design, install, and "
        "maintain yards across Lake Havasu City. Whether you need a one-time "
        "cleanup or monthly maintenance, the review rankings "
        "here show who locals trust with their yards.",
        (
            "What kind of landscaping works in Lake Havasu City?",
            "Low-water desert landscaping dominates: rock and gravel, native "
            "and desert-adapted plants on drip irrigation, palms, and "
            "artificial turf. Local landscapers design for heat and water "
            "efficiency first.",
        ),
    ),
    "cleaning": _copy(
        "Between river-season guests, vacation rentals turning over weekly, "
        "and the fine desert dust that finds its way into everything, Lake "
        "Havasu City keeps its cleaning services busy. The companies below "
        "offer house cleaning, deep cleans, move-out cleans, and "
        "vacation-rental turnovers. Listings are ranked by real "
        "public reviews, and star ratings appear only when a business has "
        "earned real reviews.",
        (
            "Do Havasu cleaning services handle vacation rental turnovers?",
            "Many do — short-term rental turnover is a major part of the "
            "local cleaning market. Check each listing or call to confirm "
            "turnover scheduling and linen service.",
        ),
    ),
    "boat-and-watercraft-rentals": _copy(
        "The lake is the whole point — and the boat and watercraft rentals "
        "below put you on it. From pontoons and ski boats to jet skis, kayaks, "
        "and paddleboards, local outfitters in Lake Havasu City rent by the "
        "half-day, day, or week. Summer and holiday weekends book out early, so "
        "reserve ahead. Listings are ranked by real public reviews; "
        "sponsored placements are labeled.",
        (
            "Do I need a license to rent a boat in Arizona?",
            "Arizona doesn't require a recreational boating license for most "
            "renters, though rules and minimum ages vary by craft and operator. "
            "Confirm requirements, deposits, and age limits with the rental "
            "company when you book.",
        ),
    ),
    # Batch 2 (2026-06-11): Auto, RV & Marine — the detailing leaves central to
    # the /chat "boat detailers" fix, plus the newly-indexed thin leaves that
    # most need unique copy now that every category publishes its own page.
    "auto-marine-detailing": _copy(
        "Havasu sun and hard lake water are brutal on a finish — water spotting, "
        "oxidized gel coat, and faded vinyl show up fast. The detailers below "
        "work on boats, cars, RVs, and trucks across Lake Havasu City, from "
        "wash-and-wax and ceramic coating to oxidation removal, interior "
        "shampoo, and pre-sale details. Whether your hull just came off the "
        "water or your daily driver bakes in the lot all summer, listings are "
        "ranked by real public reviews — never paid placement.",
        (
            "Do these detailers do boats as well as cars?",
            "Many local detailers handle both — boat and watercraft detailing "
            "(oxidation removal, hull cleaning, vinyl and upholstery) alongside "
            "auto and RV work. Check each listing or call to confirm they take "
            "watercraft.",
        ),
        (
            "Why does boat detailing matter in Lake Havasu?",
            "Constant sun and mineral-heavy lake water oxidize gel coat and leave "
            "hard-water spots that dull a finish. Regular detailing and "
            "protective coatings help boats and vehicles hold up to the desert "
            "and the lake.",
        ),
    ),
    "auto-detailing": _copy(
        "Desert dust, monsoon grime, and relentless UV take a toll on a "
        "vehicle's paint and interior. The auto detailers below serve Lake "
        "Havasu City with everything from express wash-and-wax to full interior "
        "shampoo, paint correction, ceramic coatings, and pre-sale details. "
        "Mobile detailers who come to your home or driveway are common locally. "
        "Listings are ranked by real public reviews, so the shops that keep cars "
        "looking new rank first.",
        (
            "Do Havasu detailers offer mobile service?",
            "Many local detailers will come to your home, office, or driveway — "
            "mobile detailing is common in Lake Havasu City. Check each listing "
            "or call to confirm mobile availability and service area.",
        ),
    ),
    "boat-repair-and-service": _copy(
        "Outboards, sterndrives, and trailers all take a beating on Lake Havasu "
        "— heat, ethanol fuel, and hard running hours add up. The boat repair "
        "and service shops below serve Lake Havasu City with engine work, "
        "lower-unit service, electrical and electronics, fiberglass and "
        "gel-coat repair, winterizing, and trailer fixes. Peak season fills the "
        "schedule fast, so book service before the busy river weekends. "
        "Listings are ranked by real public reviews.",
        (
            "When should I schedule boat service in Havasu?",
            "Many local shops get slammed heading into spring and summer river "
            "season, so booking routine service in the cooler months or well "
            "ahead of a trip avoids the longest waits.",
        ),
    ),
    "boat-sales": _copy(
        "Lake Havasu is one of the country's boating capitals, and the boat "
        "dealers below serve buyers and sellers across the area — new and used "
        "pontoons, ski and wakeboard boats, deck boats, personal watercraft, "
        "and the gear to go with them. Many also handle parts, service, "
        "financing, and trade-ins. Whether you're upgrading or buying your "
        "first boat, listings are ranked by real public reviews, never by who "
        "paid.",
        (
            "Do Havasu boat dealers handle service and parts too?",
            "Many do — local dealers often run a service department and parts "
            "counter alongside sales, and several take trade-ins. Check each "
            "listing for what they stock and service.",
        ),
    ),
    "boat-and-rv-storage-service": _copy(
        "Between river-season boats and a big snowbird RV crowd, Lake Havasu "
        "City runs on storage. The boat and RV storage options below offer "
        "covered and enclosed spaces, open lots, and dry-stack or yard parking, "
        "with some sites adding service, wash, and detailing. Desert sun is hard "
        "on hulls, tires, and seals, so covered storage is worth weighing. "
        "Listings are ranked by real public reviews.",
        (
            "Is covered storage worth it for a boat or RV here?",
            "Sustained sun and heat fade gel coat, crack seals, and age tires "
            "faster in the desert, so many locals choose covered or enclosed "
            "storage for boats and RVs they want to protect long-term.",
        ),
    ),
    "rv-sales-and-service": _copy(
        "Lake Havasu City draws RVers and snowbirds all winter, and the RV "
        "dealers and service shops below serve them — new and used motorhomes, "
        "fifth wheels, and travel trailers, plus repairs, appliance and AC "
        "work, roof and seal resealing, and parts. Desert heat is tough on "
        "rooftop ACs and rubber seals, so seasonal service matters. Listings "
        "are ranked by real public reviews, and ratings show only when a "
        "business has earned them.",
        (
            "Why does RV service matter in the desert?",
            "Rooftop AC units, rubber roofs, and door and window seals all "
            "degrade faster under constant Havasu sun and heat — regular "
            "inspection and resealing helps prevent leaks and breakdowns.",
        ),
    ),
    "towing-and-roadside": _copy(
        "A dead battery in July or a breakdown on a remote desert highway is no "
        "place to wait long. The towing and roadside services below serve Lake "
        "Havasu City and the surrounding routes with jump-starts, tire changes, "
        "lockouts, fuel delivery, and light- and heavy-duty towing. Summer heat "
        "drives a spike in battery and overheating calls. Listings are ranked "
        "by real public reviews; sponsored placements are labeled.",
        (
            "Is 24-hour towing available in Lake Havasu?",
            "Many local towing companies run 24/7 or after-hours service, but "
            "coverage varies — check each listing's hours and keep a number "
            "saved before a summer breakdown.",
        ),
    ),
    "tires": _copy(
        "Desert heat and hot pavement wear tires faster and raise the odds of a "
        "summer blowout, so the tire shops below serve Lake Havasu City with "
        "new tires, repairs, rotations, balancing, and alignments for cars, "
        "trucks, RVs, and trailers. Trailer and RV tires especially dry-rot in "
        "the sun, so age matters as much as tread. Listings are ranked by real "
        "public reviews, never by who paid.",
        (
            "Why do tires fail faster in Lake Havasu's heat?",
            "Hot roads and sustained high temperatures raise tire pressure and "
            "accelerate wear and dry-rot — RV and trailer tires that sit in the "
            "sun can age out before the tread wears down.",
        ),
    ),
    "car-wash": _copy(
        "Desert dust, monsoon mud, and lake trips keep Lake Havasu City's car "
        "washes busy year-round. The options below range from express tunnels "
        "and touchless bays to self-serve stalls and full-service hand washes, "
        "with several offering unlimited monthly plans. Rinsing off hard-water "
        "and dust buildup helps protect paint in the harsh sun. Listings are "
        "ranked by real public reviews, so the washes locals return to rank "
        "first.",
        (
            "Are there self-serve and express car washes in Havasu?",
            "Yes — Lake Havasu City has a mix of express tunnels, touchless "
            "automatics, self-serve bays, and full-service hand washes. Check "
            "each listing for the type and any monthly plans.",
        ),
    ),
    # Batch 3 (2026-06-11): Health & Medical. No medical advice or fabricated
    # specifics — services + local context only, with crisis/emergency notes
    # where the category warrants it (911, 988).
    "primary-care": _copy(
        "From annual physicals and chronic-condition management to walk-in sick "
        "visits, the primary care doctors and clinics below serve Lake Havasu "
        "City. With a large retiree and seasonal-resident population, many local "
        "practices cover internal and family medicine and accept Medicare, and "
        "several see new patients. Listings are ranked by real public reviews, "
        "so well-reviewed offices surface first — never paid placement. Confirm "
        "insurance and new-patient availability when you call.",
        (
            "Do Lake Havasu primary care offices take new patients?",
            "Many do, but availability shifts with the season and the area's "
            "growing population — call ahead to confirm new-patient status, "
            "insurance, and Medicare acceptance.",
        ),
    ),
    "pharmacies": _copy(
        "Prescriptions, vaccinations, and over-the-counter needs — the "
        "pharmacies below serve Lake Havasu City, from national chains with "
        "drive-thru and extended hours to independent and compounding "
        "pharmacies. With a large retiree population, several offer medication "
        "packaging, delivery, and immunizations. Listings are ranked by real "
        "public reviews; star ratings appear only when a pharmacy has earned "
        "real reviews. Check each listing for hours and services.",
        (
            "Are there 24-hour or extended-hours pharmacies in Havasu?",
            "Some chain pharmacies offer extended hours and drive-thru service, "
            "though true 24-hour coverage is limited — check each listing's "
            "hours and call to confirm before a late run.",
        ),
    ),
    "chiropractic": _copy(
        "Back and neck pain, sports and auto-injury recovery, and routine "
        "adjustments — the chiropractors below serve Lake Havasu City. Many "
        "local offices pair spinal adjustment with massage, rehab exercises, "
        "and other therapies, and several handle personal-injury and insurance "
        "cases. Listings are ranked by real public reviews, so the offices "
        "locals return to rank first. Confirm techniques and insurance when you "
        "book.",
        (
            "Do Havasu chiropractors take insurance and injury claims?",
            "Many local chiropractic offices bill insurance and handle auto- or "
            "personal-injury cases, but coverage and intake vary — confirm with "
            "the office before your first visit.",
        ),
    ),
    "physical-therapy": _copy(
        "Post-surgery rehab, sports injuries, balance and fall prevention, and "
        "chronic-pain management — the physical therapists below serve Lake "
        "Havasu City. With a large active-retiree population, many local clinics "
        "focus on orthopedic and senior rehab, and several work directly with "
        "area surgeons and physicians. Listings are ranked by real public "
        "reviews; sponsored placements, if any, are clearly labeled. Check each "
        "listing for specialties and insurance.",
        (
            "Do I need a referral for physical therapy?",
            "Requirements vary by clinic and insurance plan — some visits are "
            "available without a physician referral, but your insurer may "
            "require one for coverage. Check with the clinic and your plan "
            "before booking.",
        ),
    ),
    "eye-care": _copy(
        "Eye exams, glasses and contacts, and management of conditions like "
        "glaucoma, cataracts, and dry eye — the eye doctors and optometrists "
        "below serve Lake Havasu City. Desert sun and glare make UV protection "
        "a real consideration here, and the area's older population drives "
        "steady demand for cataract and retina care. Listings are ranked by "
        "real public reviews. Confirm whether an office handles your needs and "
        "insurance.",
        (
            "Optometrist or ophthalmologist — which do I need?",
            "Optometrists handle exams, glasses, contacts, and routine eye "
            "health; ophthalmologists are medical doctors who also do surgery "
            "and treat complex disease. Check each listing to confirm what an "
            "office offers.",
        ),
    ),
    "urgent-care-and-er": _copy(
        "For sprains, fevers, minor cuts, and the bugs that travel through town "
        "in season, the urgent care clinics below serve Lake Havasu City as a "
        "faster, lower-cost alternative to the ER for non-emergencies; summer "
        "also brings heat-related visits. Listings are ranked by real public "
        "reviews, and hours vary by location. For any life-threatening "
        "emergency, call 911 — urgent care is for non-emergency needs.",
        (
            "Urgent care or the ER?",
            "Urgent care handles non-emergencies like minor injuries, fevers, "
            "and infections, usually faster and cheaper. For chest pain, trouble "
            "breathing, severe bleeding, or any life-threatening emergency, call "
            "911 or go to the ER.",
        ),
    ),
    "senior-care-and-assisted-living": _copy(
        "Lake Havasu City's large retiree population supports a wide range of "
        "senior care — the assisted living communities, in-home care agencies, "
        "and senior services below serve the area. Options span independent and "
        "assisted living, memory care, and non-medical home help with daily "
        "tasks. Choosing care is personal, so tour and compare. Listings are "
        "ranked by real public reviews; Ask Hava doesn't sell placement and "
        "isn't a care referral service.",
        (
            "What's the difference between assisted living and in-home care?",
            "Assisted living is a residential community with on-site support; "
            "in-home care brings caregivers to the person's own home. Many "
            "families compare both — tour communities, interview agencies, and "
            "verify licensing and services directly.",
        ),
    ),
    "dermatology-and-skin": _copy(
        "In a place with this much sun, skin care isn't cosmetic — it's "
        "maintenance. The dermatologists and skin clinics below serve Lake "
        "Havasu City with skin-cancer screenings, mole and lesion checks, acne "
        "and rosacea treatment, and cosmetic procedures. The desert's intense "
        "UV makes regular skin checks worth scheduling. Listings are ranked by "
        "real public reviews. Confirm whether an office handles medical, "
        "surgical, or cosmetic dermatology.",
        (
            "How often should I get a skin check in the desert?",
            "Many people in high-sun areas schedule regular skin-cancer "
            "screenings, and more often with heavy sun exposure or a history of "
            "skin cancer. Ask a dermatologist about the right interval for you.",
        ),
    ),
    "mental-and-behavioral-health": _copy(
        "Counseling, therapy, psychiatry, and substance-use support — the "
        "mental and behavioral health providers below serve Lake Havasu City. "
        "Local options include individual, family, and group therapy, "
        "telehealth, and medication management, with some offices seeing new "
        "clients and accepting insurance. Listings are ranked by real public "
        "reviews. If you're in crisis, call or text 988 for the Suicide & "
        "Crisis Lifeline — these listings are for non-emergency care.",
        (
            "How do I find a therapist that fits in Lake Havasu?",
            "Think about what you want — therapy type, specialty, insurance, "
            "in-person or telehealth — then check each listing or call. Many "
            "providers offer a brief consult to see if it's a fit. In a crisis, "
            "call or text 988.",
        ),
    ),
    # Batch 4 (2026-06-11): Pets. Desert hazards (heat, foxtails, snakes,
    # scorpions) are real local context; no fabricated specifics.
    "grooming": _copy(
        "Full grooms, baths, nail trims, and de-shedding — the pet groomers "
        "below serve Lake Havasu City. Long, hot summers make coat care and "
        "de-shedding matter for comfort, and many local groomers handle dogs "
        "and cats, with some offering mobile service that comes to you. "
        "Listings are ranked by real public reviews, so the groomers locals "
        "rebook rank first. Check each listing for breeds, services, and "
        "walk-in availability.",
        (
            "Are there mobile pet groomers in Lake Havasu?",
            "Yes — several local groomers offer mobile service that comes to "
            "your home, which can be easier on anxious pets and in the summer "
            "heat. Check each listing to confirm mobile availability.",
        ),
        (
            "Does my dog need more grooming in the desert heat?",
            "Many owners keep up regular grooming and de-shedding in summer to "
            "help pets stay comfortable; the right coat length depends on the "
            "breed, so ask your groomer.",
        ),
    ),
    "veterinarians": _copy(
        "Wellness exams, vaccinations, dental care, surgery, and sick visits — "
        "the veterinarians below serve Lake Havasu City. Many local clinics "
        "treat dogs, cats, and sometimes exotics, and several offer urgent or "
        "after-hours options. Desert hazards like heat, foxtails, and the "
        "occasional snake or scorpion make a trusted vet worth having. Listings "
        "are ranked by real public reviews. Not every clinic offers 24-hour "
        "care, so confirm emergency hours ahead of time.",
        (
            "Is there an emergency vet in Lake Havasu City?",
            "Some clinics offer urgent or after-hours care, but 24-hour "
            "emergency coverage is limited locally — check each listing's hours "
            "and keep an emergency option saved before you need it.",
        ),
        (
            "What desert hazards should Havasu pet owners watch for?",
            "Summer heat and hot pavement, foxtails and cactus, and the "
            "occasional rattlesnake or scorpion are common local concerns. Ask "
            "your vet about heat safety and whether rattlesnake vaccines make "
            "sense.",
        ),
    ),
    "pet-stores-and-supplies": _copy(
        "Food, treats, toys, tanks, and the gear that keeps pets happy — the "
        "pet stores below serve Lake Havasu City, from national chains to "
        "independent shops. Several carry specialty and prescription diets, "
        "live fish and reptiles, or self-serve dog wash stations. Listings are "
        "ranked by real public reviews; star ratings appear only when a store "
        "has earned real reviews. Check each listing for what they stock.",
        (
            "Are there self-serve dog wash stations in Havasu?",
            "Some local pet stores offer self-serve dog wash stations — handy in "
            "the summer heat. Check each listing or call to confirm availability "
            "and pricing.",
        ),
    ),
    "training": _copy(
        "Puppy basics, obedience, behavior issues, and board-and-train — the "
        "dog trainers below serve Lake Havasu City. Local options range from "
        "group classes to private and in-home sessions, and some offer "
        "desert-specific training like rattlesnake avoidance. Listings are "
        "ranked by real public reviews, so the trainers locals recommend rank "
        "first. Check each listing for methods, class types, and the ages or "
        "issues they work with.",
        (
            "Is rattlesnake avoidance training available in Lake Havasu?",
            "Yes — some local trainers offer rattlesnake avoidance for dogs, "
            "which is popular given the desert setting. Check each listing or "
            "call to confirm clinics and scheduling.",
        ),
    ),
    "boarding-and-daycare": _copy(
        "Heading out of town, or just need your dog to burn energy for the day "
        "— the pet boarding and daycare options below serve Lake Havasu City. "
        "Local facilities offer overnight boarding, daycare, climate-controlled "
        "kennels, and sometimes grooming or training add-ons. Air conditioning "
        "isn't optional here in summer, so ask. Listings are ranked by real "
        "public reviews. Confirm vaccination requirements and availability, "
        "especially around holidays.",
        (
            "Do Havasu boarding facilities require vaccinations?",
            "Most do — proof of core vaccinations is standard for boarding and "
            "daycare. Check each listing's requirements and book early around "
            "holidays and peak travel weekends.",
        ),
    ),
    "pet-sitting": _copy(
        "For pets that do better at home, the pet sitters and dog walkers below "
        "serve Lake Havasu City — drop-in visits, dog walking, overnight stays, "
        "and vacation care. In-home sitting can be less stressful than boarding "
        "for some animals and keeps a routine going. Listings are ranked by "
        "real public reviews; Ask Hava doesn't sell placement. Confirm "
        "services, insurance or bonding, and availability before you travel.",
        (
            "Should a pet sitter be insured or bonded?",
            "Many professional pet sitters carry insurance or bonding — worth "
            "asking about, along with how they handle keys, medications, and "
            "emergencies. Confirm the details before your trip.",
        ),
    ),
    # Batch 5 (2026-06-11): the remaining thin/newly-indexed leaves — the ones
    # the generic fallback served least well once the publish gate dropped to 1.
    "casinos-and-gaming": _copy(
        "A night of slots, tables, or gaming-style entertainment — the casinos "
        "and gaming venues below serve the Lake Havasu City area. Listings are "
        "ranked by real public reviews, so well-reviewed spots surface first, "
        "and star ratings appear only when a venue has earned real reviews. "
        "Check each listing for location, hours, age requirements, and what "
        "games or entertainment they offer before you go.",
        (
            "Is there a casino in Lake Havasu City?",
            "Local gaming options are limited — check the listings here for "
            "what's available, including location and hours, since the nearest "
            "full casinos may be a drive away.",
        ),
    ),
    "nutrition-and-wellness": _copy(
        "Dietitians, nutrition coaching, supplements, IV hydration, and general "
        "wellness services — the nutrition and wellness providers below serve "
        "Lake Havasu City. In a hot, active climate, hydration and recovery get "
        "real attention here. Listings are ranked by real public reviews; Ask "
        "Hava doesn't sell placement and isn't a medical or nutrition adviser. "
        "Check each listing for services and credentials, and consult a doctor "
        "for medical concerns.",
        (
            "What do nutrition and wellness providers in Havasu offer?",
            "Services range from registered-dietitian counseling and meal "
            "planning to supplements, IV hydration, and wellness coaching. "
            "Offerings and credentials vary, so check each listing and verify "
            "qualifications.",
        ),
    ),
    "martial-arts": _copy(
        "Karate, jiu-jitsu, kickboxing, and kids' programs — the martial arts "
        "studios below serve Lake Havasu City. Local dojos and gyms offer "
        "classes for all ages, from little-kids and after-school programs to "
        "adult fitness and competition training. Listings are ranked by real "
        "public reviews, so the studios families stick with rank first. Check "
        "each listing for styles, age groups, and trial classes.",
        (
            "Are there kids' martial arts classes in Lake Havasu?",
            "Yes — many local studios run children's programs alongside adult "
            "classes, often with trial sessions. Check each listing for age "
            "groups, styles, and intro offers.",
        ),
    ),
    "personal-training": _copy(
        "One-on-one coaching, small-group sessions, and custom programs — the "
        "personal trainers below serve Lake Havasu City. Local trainers work in "
        "gyms, private studios, and in-home or outdoor settings, covering "
        "weight loss, strength, sport-specific, and senior fitness. Listings "
        "are ranked by real public reviews, so trainers clients stick with rank "
        "first. Check each listing for specialties, settings, and whether they "
        "offer a consult.",
        (
            "Do Havasu personal trainers do in-home or outdoor sessions?",
            "Many local trainers offer in-home, outdoor, or virtual sessions "
            "alongside gym training — handy for scheduling around the heat. "
            "Check each listing or ask about options.",
        ),
    ),
    "handyman": _copy(
        "Small repairs, mounting, assembly, drywall patches, and the odd jobs "
        "that don't need a specialty contractor — the handyman services below "
        "serve Lake Havasu City. Many local handymen cover both interior and "
        "exterior work, plus rental and vacation-home upkeep. Listings are "
        "ranked by real public reviews. For larger or specialized jobs, check "
        "whether the work needs a licensed contractor in Arizona.",
        (
            "When do I need a licensed contractor instead of a handyman?",
            "Arizona requires a licensed contractor for projects above a small "
            "dollar threshold and for certain trades. Minor repairs are fine "
            "for a handyman; for bigger work, confirm licensing — Ask Hava "
            "doesn't verify it.",
        ),
    ),
    "shipping-and-postal": _copy(
        "Packages, mailboxes, notary, printing, and freight — the shipping and "
        "postal stores below serve Lake Havasu City. Local pack-and-ship shops "
        "handle UPS, FedEx, and USPS drop-offs, private mailboxes, passport "
        "photos, and packing supplies — handy for snowbirds and vacation-home "
        "owners managing mail seasonally. Listings are ranked by real public "
        "reviews. Check each listing for carriers and services.",
        (
            "Can I rent a private mailbox in Lake Havasu City?",
            "Yes — several local shipping stores offer private mailbox rental "
            "with a street address, useful for seasonal residents and home "
            "businesses. Check each listing for box sizes and mail forwarding.",
        ),
    ),
    "event-planning": _copy(
        "Weddings, parties, corporate events, and lakeside celebrations — the "
        "event planners below serve Lake Havasu City. From full-service "
        "coordination to day-of management, local planners handle venues, "
        "vendors, rentals, and timelines, including destination weddings drawn "
        "to the lake and the London Bridge backdrop. Listings are ranked by "
        "real public reviews; sponsored placements are labeled. Check each "
        "listing for the events they specialize in.",
        (
            "Do Havasu event planners do destination weddings?",
            "Many local planners coordinate destination and lakeside weddings "
            "with area venues and vendors. Check each listing for specialties, "
            "packages, and whether they handle full planning or day-of "
            "coordination.",
        ),
    ),
    "notary": _copy(
        "Document signings, acknowledgments, and loan closings — the notaries "
        "below serve Lake Havasu City. Local options include mobile notaries "
        "who travel to your home, office, or hospital, plus shipping stores and "
        "other businesses offering notary service. Mobile and after-hours "
        "service is common for time-sensitive paperwork. Listings are ranked by "
        "real public reviews. Confirm ID requirements and fees before your "
        "appointment.",
        (
            "Are there mobile notaries in Lake Havasu City?",
            "Yes — several local notaries travel to you, which helps for "
            "hospital signings, real-estate closings, and after-hours needs. "
            "Check each listing for mobile service, hours, and fees.",
        ),
    ),
    "title-and-escrow": _copy(
        "Closing on a home or refinancing — the title and escrow companies "
        "below serve Lake Havasu City. Local offices handle title searches, "
        "title insurance, escrow, and closing coordination for buyers, sellers, "
        "and lenders in the area's active and seasonal real-estate market. "
        "Listings are ranked by real public reviews. Check each listing for "
        "services, and confirm details directly when coordinating a closing.",
        (
            "What does a title and escrow company do?",
            "They research and insure clear title, hold funds in escrow, and "
            "coordinate the paperwork and closing between buyer, seller, and "
            "lender. Your agent or lender often recommends one, but you can "
            "compare.",
        ),
    ),
    "tutoring-and-test-prep": _copy(
        "Reading and math help, homework support, and SAT, ACT, and test prep — "
        "the tutors and tutoring centers below serve Lake Havasu City. Local "
        "options span one-on-one, group, in-home, and online sessions across "
        "K-12 and college subjects, with some focused on specific exams. "
        "Listings are ranked by real public reviews. Check each listing for "
        "subjects, grade levels, and formats.",
        (
            "Is online and in-home tutoring available in Havasu?",
            "Yes — many local tutors offer in-home and online sessions alongside "
            "center-based help. Check each listing for subjects, grade levels, "
            "and scheduling.",
        ),
    ),
    "music-lessons": _copy(
        "Piano, guitar, voice, drums, and more — the music teachers and schools "
        "below serve Lake Havasu City. Local instructors offer private and "
        "group lessons for kids and adults, in studios, in-home, or online, for "
        "beginners through advanced players. Listings are ranked by real public "
        "reviews, so the teachers students stick with rank first. Check each "
        "listing for instruments, ages, and lesson formats.",
        (
            "Do Havasu music teachers take adult beginners?",
            "Many do — local instructors teach all ages and levels, including "
            "adult beginners, in studio, in-home, or online formats. Check each "
            "listing for instruments and scheduling.",
        ),
    ),
    "post-office": _copy(
        "Mailing, shipping, PO boxes, and passport services — the post office "
        "locations below serve Lake Havasu City. For USPS branch hours, PO box "
        "rental, and passport appointments, check the listing details, and note "
        "that lobby and counter hours often differ. For private mailboxes and "
        "UPS or FedEx shipping, see the shipping and postal listings too. "
        "Listings reflect real public reviews where available.",
        (
            "How do I rent a PO box or book a passport appointment?",
            "USPS handles PO box rental and passport services at branch "
            "locations — check the listing for hours and call ahead, since "
            "passport service is often by appointment and counter hours vary.",
        ),
    ),
    "tattoo-and-piercing": _copy(
        "Whether it's a first tattoo, a cover-up, a touch-up, or a new piercing, "
        "the studios below serve Lake Havasu City with custom work, flash, and "
        "body piercing. A good shop walks you through the design, pricing, and "
        "aftercare before any needle comes out — and in Havasu's sun, keeping "
        "fresh ink covered and out of the lake while it heals matters. Listings "
        "are built from real public reviews and rotate daily, so the artists "
        "locals come back to stay easy to find; any sponsored placement is "
        "clearly labeled.",
        (
            "What should I check before booking a tattoo in Lake Havasu City?",
            "Look through the artist's healed-work portfolio for the style you "
            "want, read the public reviews, and ask about pricing, deposits, and "
            "aftercare up front. A consultation before you commit is normal and a "
            "good sign.",
        ),
        (
            "Do these studios do piercings as well as tattoos?",
            "Many Lake Havasu tattoo studios also offer body piercing, though not "
            "all do, and piercing is sometimes handled by a dedicated piercer on "
            "set days. Check the individual listing or call ahead to confirm what "
            "each shop offers.",
        ),
    ),
}


def copy_for_leaf(slug: str | None) -> LeafCopy | None:
    """Curated :class:`LeafCopy` for ``slug``, or ``None`` (generic fallback)."""
    if not slug:
        return None
    return LEAF_COPY.get(slug.strip().lower())
