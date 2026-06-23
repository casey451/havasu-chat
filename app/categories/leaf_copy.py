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
