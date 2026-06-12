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
        "By real public reviews — more reviews, more weight, so a strong rating "
        "across many reviews beats a perfect score from only a couple. Spots "
        "can't be bought, Hava never invents a rating, and any sponsored "
        "placement is clearly labeled.",
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
    "auto-repair": _copy(
        "Desert heat is hard on cars — batteries cook, coolant systems work "
        "overtime, and AC failures turn a Havasu commute miserable fast. The "
        "auto repair shops below serve Lake Havasu City with everything from "
        "oil changes and brakes to diagnostics, AC work, and major engine and "
        "transmission jobs. Listings are ranked by real public "
        "reviews, so shops locals actually trust rank first.",
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
        "families. Listings are ranked by real public reviews, so "
        "well-reviewed practices surface first — never paid placement.",
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
        "rolling over a 401(k) or building an income plan, the real "
        "review rankings here surface well-reviewed local offices first. "
        "Ask Hava doesn't sell placement, and isn't a financial adviser itself.",
    ),
    "hair-salons-and-barbers": _copy(
        "Cuts, color, blowouts, and classic barbering — the hair salons and "
        "barbers below serve Lake Havasu City. From quick walk-in trims to "
        "full-service color and styling, the listings span neighborhood shops "
        "and busier downtown salons. Listings are ranked by real "
        "public reviews, so the chairs locals book again rank first; star "
        "ratings appear only when a shop has earned real reviews.",
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
    "restaurants": _copy(
        "Lakefront patios, taco joints, steakhouses, and the spots locals "
        "actually drive across town for — the restaurants below serve Lake "
        "Havasu City. Whether you want waterfront dining on the Channel, a "
        "quick bite, or a sit-down dinner, the review rankings "
        "here put consistently well-reviewed kitchens first. Hours swing with "
        "the season, so check each listing before you go.",
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
}


def copy_for_leaf(slug: str | None) -> LeafCopy | None:
    """Curated :class:`LeafCopy` for ``slug``, or ``None`` (generic fallback)."""
    if not slug:
        return None
    return LEAF_COPY.get(slug.strip().lower())
