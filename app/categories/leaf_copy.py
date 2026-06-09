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
        "The list is server-rendered from our local directory and updates as "
        "businesses are added or verified.",
    ),
    (
        "How are these {name_lower} ranked?",
        "By a volume-weighted rating: a business with a strong rating across many "
        "reviews ranks above one with a perfect score from only a couple of "
        "reviews. We don't sell ranking positions — any sponsored placement is "
        "clearly labeled.",
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
        "transmission jobs. Listings are ranked by volume-weighted public "
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
        "Listings are ranked by volume-weighted public reviews; sponsored "
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
        "volume-weighted public reviews.",
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
        "families. Listings are ranked by volume-weighted public reviews, so "
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
        "volume-weighted public reviews, and ratings appear only when a "
        "business has earned real reviews.",
    ),
    "roofing": _copy(
        "Havasu roofs take a beating: triple-digit summers, intense UV, and "
        "monsoon winds that find every loose tile. The roofers below handle "
        "repairs, replacements, coatings, and inspections across Lake Havasu "
        "City — tile, shingle, and the foam and flat roofs common on desert "
        "homes. Listings are ranked by volume-weighted public reviews, never by "
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
        "property. Listings are ranked by volume-weighted public reviews; "
        "Ask Hava doesn't sell ranking and labels any sponsored placement.",
    ),
    "insurance": _copy(
        "Home, auto, boat, RV, and business — the insurance agents below serve "
        "Lake Havasu City. Watercraft and RV coverage matter more here than in "
        "most towns, and desert homes have their own monsoon and sun "
        "considerations. Many local agents write multiple lines and bundle "
        "policies. Listings are ranked by volume-weighted public reviews, and "
        "ratings show only when a business has earned them.",
    ),
    "financial-advisors": _copy(
        "Retirement planning, investments, and tax-aware strategy — the "
        "financial advisors and planners below serve Lake Havasu City, a town "
        "with a large retiree and second-home population. Whether you're "
        "rolling over a 401(k) or building an income plan, the volume-weighted "
        "review rankings here surface well-reviewed local offices first. "
        "Ask Hava doesn't sell placement, and isn't a financial adviser itself.",
    ),
    "hair-salons-and-barbers": _copy(
        "Cuts, color, blowouts, and classic barbering — the hair salons and "
        "barbers below serve Lake Havasu City. From quick walk-in trims to "
        "full-service color and styling, the listings span neighborhood shops "
        "and busier downtown salons. Listings are ranked by volume-weighted "
        "public reviews, so the chairs locals book again rank first; star "
        "ratings appear only when a shop has earned real reviews.",
    ),
    "hotels-and-motels": _copy(
        "From channel-side resorts to budget motels and everything between, the "
        "hotels and motels below serve visitors to Lake Havasu City. Rates and "
        "availability swing hard with the seasons — spring break, summer river "
        "weekends, and the Balloon Festival book out fast — so plan ahead for "
        "peak dates. Listings are ranked by volume-weighted public reviews, "
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
        "quick bite, or a sit-down dinner, the volume-weighted review rankings "
        "here put consistently well-reviewed kitchens first. Hours swing with "
        "the season, so check each listing before you go.",
        (
            "Are there waterfront restaurants in Lake Havasu City?",
            "Yes — several restaurants sit along the Channel and the lakefront. "
            "Use each listing's location and hours to find one near the water, "
            "and call ahead on busy river weekends.",
        ),
    ),
    "boat-and-watercraft-rentals": _copy(
        "The lake is the whole point — and the boat and watercraft rentals "
        "below put you on it. From pontoons and ski boats to jet skis, kayaks, "
        "and paddleboards, local outfitters in Lake Havasu City rent by the "
        "half-day, day, or week. Summer and holiday weekends book out early, so "
        "reserve ahead. Listings are ranked by volume-weighted public reviews; "
        "sponsored placements are labeled.",
        (
            "Do I need a license to rent a boat in Arizona?",
            "Arizona doesn't require a recreational boating license for most "
            "renters, though rules and minimum ages vary by craft and operator. "
            "Confirm requirements, deposits, and age limits with the rental "
            "company when you book.",
        ),
    ),
}


def copy_for_leaf(slug: str | None) -> LeafCopy | None:
    """Curated :class:`LeafCopy` for ``slug``, or ``None`` (generic fallback)."""
    if not slug:
        return None
    return LEAF_COPY.get(slug.strip().lower())
