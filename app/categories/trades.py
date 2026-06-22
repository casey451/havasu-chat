"""Dedicated home-services trade pages (SEO P2.1/P2.2).

Promotes the home-services trade *facet* to real, server-rendered URLs:
``/categories/home-property-services/{trade}`` for exactly the ten most
winnable trades. Each page draws the SAME provider pool as the parent
``/categories/home-property-services`` listing (``route_provider_filter``),
narrowed by the trade needle-matching that previously powered the legacy
``?trade=`` facet on the singular ``/category/`` family — the matcher moved
here so both the retired facet plumbing (``app.api.routes.category_pages``)
and the new pages share one implementation instead of duplicating it.

Scaled-content gate (Google policy note in the SEO brief): a trade with fewer
than :data:`TRADE_PAGE_MIN_PROVIDERS` active providers 404s, is excluded from
the sitemap, and is never linked — thin near-empty pages are not exposed.

Decision D4 (Casey, final): trade pages emit ``BreadcrumbList`` + ``ItemList``
JSON-LD only. NO self-serving ``AggregateRating`` structured data anywhere on
these pages — visible star ratings in the cards stay, structured-data ratings
are omitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.categories import queries as cat_queries
from app.db.models import Provider

#: Scaled-content thin-page gate — a trade page publishes (resolves, joins the
#: sitemap, gets linked) only at/above this many ACTIVE non-draft providers.
TRADE_PAGE_MIN_PROVIDERS = 3

#: The parent category route the ten trades live under.
TRADE_PARENT_SLUG = "home-property-services"

#: A.3 taxonomy department that owns the trades' leaf twins.
TRADE_LEAF_DEPARTMENT_SLUG = "home-and-property-services"

#: Curated trade slug -> its A.3 taxonomy-leaf twin. With the taxonomy nav
#: live, the leaf pages are the canonical SEO surface for these trades; a
#: trade URL 301s to its twin whenever the twin ships (clears the leaf gate),
#: so two pages never compete for the same search term ("lake havasu
#: plumbers"). ``garage-door`` has no leaf twin — its curated page stays.
LEAF_TWINS: dict[str, str] = {
    "plumbers": "plumbing",
    "hvac": "hvac",
    "electricians": "electrical",
    "pool-service": "pools-and-spas",
    "pest-control": "pest-control",
    "roofers": "roofing",
    "landscapers": "landscaping-and-lawn",
    "cleaning": "cleaning",
    "handyman": "handyman",
}


@dataclass(frozen=True)
class Trade:
    """One promoted trade under :data:`TRADE_PARENT_SLUG`.

    ``slug`` is the URL segment; ``label`` the plural display noun ("Plumbers");
    ``singular`` the singular noun used in templated copy ("plumber");
    ``needles`` the lowercase tokens matched (substring) against a provider's
    Google primary type, Google categories, legacy category, and curated
    ``attributes.sub_trades`` — same algorithm as the legacy ``?trade=`` facet;
    ``intro`` the 40–100 word local intro paragraph;
    ``faqs`` templated truthful Q&A pairs — ``{n}`` / ``{label}`` / ``{singular}``
    are filled with the live provider count at render time.
    """

    slug: str
    label: str
    singular: str
    needles: frozenset[str]
    intro: str
    faqs: tuple[tuple[str, str], ...]


_COMMON_FAQS: tuple[tuple[str, str], ...] = (
    (
        "How many {label_lower} does Ask Hava list in Lake Havasu City?",
        "Ask Hava currently lists {n} {label_lower} serving Lake Havasu City, AZ. "
        "The list comes straight from our local directory and updates as "
        "businesses are added or verified.",
    ),
    (
        "How are the {label_lower} on this page ranked?",
        "By real public reviews — more reviews, more weight, so a {singular} "
        "with a strong rating across many reviews beats a perfect score from "
        "only a couple. Spots can't be bought, Hava never invents a rating, and "
        "any sponsored placement is clearly labeled.",
    ),
    (
        "Are the ratings and review counts real?",
        "Yes. Star ratings and review counts come from public Google reviews and "
        "are shown only when a business has at least a few reviews. Ask Hava "
        "never fabricates a rating.",
    ),
    (
        "How do I get a {singular} added to or corrected on this page?",
        "Use the Contribute link in the site footer, or open the business's page "
        "and report wrong info. Local corrections are reviewed before they go "
        "live.",
    ),
)


def _faqs_for(extra: tuple[tuple[str, str], ...] = ()) -> tuple[tuple[str, str], ...]:
    """Common four truthful Q&As plus up to two trade-specific ones (4–6 total)."""
    return _COMMON_FAQS + extra[:2]


# The ten promoted trades (SEO brief P2.1). Needle sets are curated per trade:
# underscore forms match Google type tokens / sub_trades, space forms match the
# free-text Google category labels.
TRADES: dict[str, Trade] = {
    t.slug: t
    for t in (
        Trade(
            slug="plumbers",
            label="Plumbers",
            singular="plumber",
            needles=frozenset({"plumber", "plumbing"}),
            intro=(
                "Desert water is hard on pipes — scale buildup, slab leaks, and "
                "water heaters that quit in the middle of a Havasu summer. The "
                "plumbers below serve Lake Havasu City and the surrounding area, "
                "handling everything from drain clearing and re-pipes to fixture "
                "installs and emergency calls. Ratings and review counts come from "
                "real public reviews, so you can see at a glance who locals "
                "actually call back."
            ),
            faqs=_faqs_for(
                (
                    (
                        "Do Lake Havasu plumbers handle emergency calls?",
                        "Many local plumbing companies offer emergency or same-day "
                        "service, but availability varies by company and season. "
                        "Check each listing's hours and call ahead to confirm.",
                    ),
                )
            ),
        ),
        Trade(
            slug="hvac",
            label="HVAC Companies",
            singular="HVAC company",
            needles=frozenset(
                {"hvac", "air_conditioning", "air conditioning", "heating_contractor"}
            ),
            intro=(
                "When Lake Havasu City hits 115°F, air conditioning isn't a "
                "comfort — it's a necessity. The HVAC companies below install, "
                "repair, and maintain cooling and heating systems across Havasu, "
                "from quick capacitor swaps to full system replacements. Summer "
                "is peak season here, so the smart move is a spring tune-up "
                "before the first heat wave. Ratings shown are from real public "
                "reviews."
            ),
            faqs=_faqs_for(
                (
                    (
                        "When should I service my AC in Lake Havasu?",
                        "Most local HVAC companies recommend a tune-up in spring, "
                        "before summer demand peaks — repair calls back up fast "
                        "once daily highs pass 110°F.",
                    ),
                )
            ),
        ),
        Trade(
            slug="electricians",
            label="Electricians",
            singular="electrician",
            needles=frozenset({"electrician", "electrical"}),
            intro=(
                "From panel upgrades and ceiling fans to RV hookups and boat-dock "
                "power, the electricians below serve Lake Havasu City homes and "
                "businesses. Desert heat is tough on electrical systems — AC "
                "circuits run hard for half the year — so licensed help matters. "
                "Listings are ranked by real public reviews, and "
                "ratings appear only when a business has earned real reviews."
            ),
            faqs=_faqs_for(),
        ),
        Trade(
            slug="handyman",
            label="Handyman Services",
            singular="handyman service",
            needles=frozenset({"handyman", "handyperson", "handywoman"}),
            intro=(
                "For the jobs that don't need a specialty contractor — drywall "
                "patches, door adjustments, fixture swaps, fence repairs — a good "
                "handyman is the call. The handyman services below work across "
                "Lake Havasu City, and many handle the small-project punch lists "
                "that bigger outfits won't schedule. Ratings and review counts "
                "come from real public reviews so you can compare at a glance."
            ),
            faqs=_faqs_for(),
        ),
        Trade(
            slug="pool-service",
            label="Pool Services",
            singular="pool service",
            needles=frozenset(
                {
                    "pool_service",
                    "pool service",
                    "pool_cleaning",
                    "pool cleaning",
                    "pool_repair",
                    "pool repair",
                    "swimming_pool",
                    "swimming pool",
                    "pool_contractor",
                    "pool contractor",
                }
            ),
            intro=(
                "Backyard pools work overtime in Lake Havasu City — nine-plus "
                "months of swim season means constant chemistry, filtration, and "
                "equipment wear. The pool services below handle weekly cleaning, "
                "green-pool recoveries, pump and filter repairs, and resurfacing "
                "across Havasu. Listings are ranked by real public "
                "reviews; star ratings appear only when a company has earned real "
                "reviews."
            ),
            faqs=_faqs_for(
                (
                    (
                        "How often do Havasu pools need service?",
                        "Most local pool companies recommend weekly service in "
                        "the long Havasu swim season — heat and sun burn through "
                        "chlorine far faster here than in milder climates.",
                    ),
                )
            ),
        ),
        Trade(
            slug="pest-control",
            label="Pest Control Companies",
            singular="pest control company",
            needles=frozenset({"pest_control", "pest control", "exterminator"}),
            intro=(
                "Scorpions, ants, roaches, and the occasional pack rat — desert "
                "living comes with desert pests. The pest control companies below "
                "serve Lake Havasu City with one-time treatments, recurring "
                "service plans, and home-sale inspections. Bark scorpions are the "
                "local headline act, so ask about scorpion-specific treatment if "
                "that's your concern. Ratings shown come from real public "
                "reviews."
            ),
            faqs=_faqs_for(
                (
                    (
                        "Are scorpions a problem in Lake Havasu City?",
                        "Yes — bark scorpions are common across the area, "
                        "especially in summer. Most local pest control companies "
                        "offer scorpion-specific treatments and recurring plans.",
                    ),
                )
            ),
        ),
        Trade(
            slug="roofers",
            label="Roofers",
            singular="roofer",
            needles=frozenset({"roofer", "roofing", "roof_repair", "roof repair"}),
            intro=(
                "Havasu roofs take a beating: triple-digit summers, intense UV, "
                "and monsoon winds that find every loose tile. The roofers below "
                "handle repairs, replacements, coatings, and inspections across "
                "Lake Havasu City — tile, shingle, and the foam and flat roofs "
                "common on desert homes. Listings are ranked by real "
                "public reviews, never by who paid; sponsored slots are always "
                "labeled."
            ),
            faqs=_faqs_for(
                (
                    (
                        "When is roofing season in Lake Havasu?",
                        "Roof work happens year-round, but many locals schedule "
                        "inspections before monsoon season (roughly June–"
                        "September) and book bigger jobs for the cooler months.",
                    ),
                )
            ),
        ),
        Trade(
            slug="garage-door",
            label="Garage Door Companies",
            singular="garage door company",
            needles=frozenset({"garage_door", "garage door"}),
            intro=(
                "A garage door that won't open in July is a genuine Havasu "
                "emergency. The garage door companies below handle spring and "
                "opener repairs, new door installs, and routine maintenance "
                "across Lake Havasu City. Desert heat shortens the life of "
                "springs and openers, so a periodic tune-up pays off. Ratings "
                "and review counts come from real public reviews — no fabricated "
                "stars."
            ),
            faqs=_faqs_for(),
        ),
        Trade(
            slug="landscapers",
            label="Landscapers",
            singular="landscaper",
            needles=frozenset({"landscap"}),
            intro=(
                "Desert landscaping is its own craft — xeriscape design, "
                "decorative rock, drip irrigation, palm trimming, and artificial "
                "turf that survives Havasu summers. The landscapers below design, "
                "install, and maintain yards across Lake Havasu City. Whether you "
                "need a one-time cleanup or monthly maintenance, the volume-"
                "weighted review rankings here show who locals trust with their "
                "yards."
            ),
            faqs=_faqs_for(
                (
                    (
                        "What kind of landscaping works in Lake Havasu City?",
                        "Low-water desert landscaping dominates: rock and gravel, "
                        "native and desert-adapted plants on drip irrigation, "
                        "palms, and artificial turf. Local landscapers design "
                        "for heat and water efficiency first.",
                    ),
                )
            ),
        ),
        Trade(
            slug="cleaning",
            label="Cleaning Services",
            singular="cleaning service",
            needles=frozenset(
                {"cleaning", "maid", "janitorial", "housekeeping"}
            ),
            intro=(
                "Between river-season guests, vacation rentals turning over "
                "weekly, and the fine desert dust that finds its way into "
                "everything, Lake Havasu City keeps its cleaning services busy. "
                "The companies below offer house cleaning, deep cleans, move-out "
                "cleans, and vacation-rental turnovers. Listings are ranked by "
                "real public reviews, and star ratings appear only "
                "when a business has earned real reviews."
            ),
            faqs=_faqs_for(
                (
                    (
                        "Do Havasu cleaning services handle vacation rental turnovers?",
                        "Many do — short-term rental turnover is a major part of "
                        "the local cleaning market. Check each listing or call to "
                        "confirm turnover scheduling and linen service.",
                    ),
                )
            ),
        ),
    )
}


def trade_by_slug(slug: str | None) -> Trade | None:
    """The promoted :class:`Trade` for ``slug``, or ``None`` when not promoted."""
    if not slug:
        return None
    return TRADES.get(slug.strip().lower())


# ---------------------------------------------------------------------------
# Trade matching — moved verbatim from app.api.routes.category_pages so the
# legacy ``?trade=`` facet plumbing and the dedicated pages share ONE matcher.
# ---------------------------------------------------------------------------


def needles_for_trade(trade_slug: str) -> frozenset[str]:
    """Lowercase needle tokens for ``trade_slug``.

    Promoted trades use their curated needle set; any other value falls back to
    the legacy generic derivation (slug with ``-``→``_`` plus a spaced variant),
    preserving the old ``?trade=`` facet behavior for unpromoted values.
    """
    promoted = trade_by_slug(trade_slug)
    if promoted is not None:
        return promoted.needles
    c = trade_slug.strip().lower().replace("-", "_")
    return frozenset({c, c.replace("_", " ")})


def provider_matches_trade(provider: Provider | None, trade_slug: str) -> bool:
    """Whether ``provider`` plies ``trade_slug``.

    Substring-matches the trade's needles against the provider's Google primary
    type, Google category labels, legacy ``category``, and curated
    ``attributes.sub_trades`` (hyphens normalised to underscores). Identical
    algorithm to the legacy ``?trade=`` facet matcher.
    """
    if provider is None:
        return False
    needles = needles_for_trade(trade_slug)
    primary = (provider.google_primary_category or "").lower()
    for n in needles:
        if n and n in primary.replace("-", "_"):
            return True
    cats = provider.google_categories or []
    if isinstance(cats, list):
        for gc in cats:
            gl = str(gc).lower()
            for n in needles:
                if n and n in gl.replace("-", "_"):
                    return True
    leg = (provider.category or "").lower()
    for n in needles:
        if n and n in leg.replace("-", "_"):
            return True
    attrs = provider.attributes or {}
    subs = attrs.get("sub_trades")
    if isinstance(subs, list):
        for s in subs:
            sl = str(s).lower().replace("-", "_")
            for n in needles:
                if n and n in sl:
                    return True
    return False


# ---------------------------------------------------------------------------
# Listing + gate
# ---------------------------------------------------------------------------


def _trade_provider_rows(db: Session, trade: Trade) -> list[Provider]:
    """ACTIVE non-draft providers on the parent route matching ``trade``.

    Reuses the parent listing's ``route_provider_filter`` pool and rating sort,
    then narrows with the shared trade matcher in Python (the needle match isn't
    SQL-expressible). Never raises — a DB hiccup degrades to an empty list.
    """
    try:
        rows: list[Provider] = (
            db.query(Provider)
            .filter(
                cat_queries.route_provider_filter(TRADE_PARENT_SLUG),
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
            )
            .order_by(*cat_queries._dampened_rating_sort_key(db))
            .limit(cat_queries._MATERIALIZE_CAP)
            .all()
        )
    except Exception:
        return []
    return [p for p in rows if provider_matches_trade(p, trade.slug)]


def trade_listing(
    db: Session, trade: Trade, *, now: datetime
) -> tuple[list[dict[str, Any]], int, list[Provider]]:
    """``(cards, total, providers)`` for a trade page.

    Cards use the SAME builder as the parent category page, so the trade page
    renders identical listing cards (rating stars, review counts, open-now,
    photo). ``providers`` rides along for the ItemList JSON-LD.
    """
    providers = _trade_provider_rows(db, trade)
    allowed = cat_queries._allowed_subcategory_slugs(TRADE_PARENT_SLUG)

    # Phase F §7.2 honesty gate: pin active paid placements for this trade to the
    # top and label them Sponsored. No-op until a placement is sold for this trade
    # slug — zero effect on the live site today.
    from app.monetization.serving import (
        ItemRating,
        active_category_creatives,
        active_category_tiers,
        apply_category_order,
        arrange_listing,
        listing_day,
    )
    from app.portal.products import daily_shuffle_enabled, mobile_paid_cap, rating_gate

    try:
        tiers = active_category_tiers(db, trade.slug)
    except Exception:
        tiers = {}  # placement lookup must never break the organic trade page
    sponsored_ids = set(tiers.values())
    try:
        creatives = active_category_creatives(db, trade.slug) if tiers else {}
    except Exception:
        creatives = {}

    new_unrated_ids: frozenset[str] = frozenset()
    by_id = {p.id: p for p in providers}
    if daily_shuffle_enabled():
        arr = arrange_listing(
            [
                ItemRating(p.id, p.google_rating, getattr(p, "google_review_count", None))
                for p in providers
            ],
            tiers,
            category_slug=trade.slug,
            day=listing_day(now),
            threshold=rating_gate(),
            cap=mobile_paid_cap(),
        )
        providers = [by_id[k] for k in arr.order if k in by_id]
        new_unrated_ids = arr.new_unrated
    elif tiers:
        providers = [
            by_id[pid]
            for pid in apply_category_order([p.id for p in providers], tiers)
            if pid in by_id
        ]

    cards = [
        cat_queries._provider_card(
            db, p, now=now, allowed_subcategories=allowed,
            sponsored_provider_ids=sponsored_ids,
            new_unrated_ids=new_unrated_ids, creatives=creatives,
        )
        for p in providers
    ]
    return cards, len(providers), providers


def trade_provider_count(db: Session, trade: Trade) -> int:
    """ACTIVE non-draft provider count for ``trade`` (the thin-page gate input)."""
    return len(_trade_provider_rows(db, trade))


def qualifying_trades(db: Session) -> list[tuple[Trade, int]]:
    """``(trade, count)`` for every promoted trade clearing the thin-page gate.

    Order follows :data:`TRADES` declaration order. Used by the sitemap and the
    parent page's trade-link row, so under-minimum trades are neither linked nor
    listed. One parent-pool query total (not one per trade).
    """
    try:
        rows: list[Provider] = (
            db.query(Provider)
            .filter(
                cat_queries.route_provider_filter(TRADE_PARENT_SLUG),
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
            )
            .limit(cat_queries._MATERIALIZE_CAP)
            .all()
        )
    except Exception:
        return []
    out: list[tuple[Trade, int]] = []
    for trade in TRADES.values():
        n = sum(1 for p in rows if provider_matches_trade(p, trade.slug))
        if n >= TRADE_PAGE_MIN_PROVIDERS:
            out.append((trade, n))
    return out
