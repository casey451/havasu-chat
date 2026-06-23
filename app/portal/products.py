"""Monetization product + ranking config (P4).

Single home for the *tunable numbers* the monetization layer reads, so none of
them are hardcoded at a call site (brief §4.1 / plan §2.1–§2.2: "build prices as
configurable values, not hardcoded"):

* **Prices** stay DATA in the ``placement_prices`` table (admin-editable without a
  deploy) — :func:`app.monetization.serving.price_for` reads them. This module
  only describes the sellable *catalog* (labels/blurbs, the same shape
  :data:`app.portal.placements.PURCHASABLE_TYPES` exposes) and an optional
  default price book the operator can seed once.
* **The non-paid ranking knobs** (the >4.0 quality gate, the mobile paid cap, and
  the daily-shuffle master switch) live here as env-overridable constants so they
  can be tuned at rollout, not in code (plan §2.2 R8: "make the >4.0 gate config
  so you can drop to ~3.8 per category").

Nothing here moves money or imports Stripe; it is pure config.
"""

from __future__ import annotations

import os

from app.bootstrap_env import ensure_dotenv_loaded

# --------------------------------------------------------------------------- #
# Non-paid ranking config (plan §2.2). All env-overridable so the operator can
# tune at rollout without a deploy.
# --------------------------------------------------------------------------- #

# The Google-rating quality gate for the *top* (rated) organic pool. A business
# with rating STRICTLY GREATER than this and at least one review rides the
# daily-shuffled rated pool; one with reviews but at/below it sinks below the
# new/unrated tail (visible, never excluded). 4.0 per the brief; tunable down to
# ~3.8 in a thin small-town category so a page never empties.
_DEFAULT_RATING_GATE = 4.0

# Never show more than this many *guaranteed* paid cards before the first organic
# result (plan §2.1: cap the guaranteed block at 3 so a phone page never reads
# "all ads"). You can still SELL five sticky tiers — the overflow stays labeled
# "Sponsored" but is no longer pinned above the fold.
_DEFAULT_MOBILE_PAID_CAP = 3

_TRUE = {"1", "true", "yes", "on"}


def _env(name: str) -> str:
    ensure_dotenv_loaded()
    return (os.environ.get(name) or "").strip()


def rating_gate() -> float:
    """The >rating quality gate for the rated organic pool (env ``RATING_GATE``)."""
    raw = _env("RATING_GATE")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return _DEFAULT_RATING_GATE


def mobile_paid_cap() -> int:
    """Max guaranteed paid cards pinned above the first organic result
    (env ``MOBILE_PAID_CAP``)."""
    raw = _env("MOBILE_PAID_CAP")
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return _DEFAULT_MOBILE_PAID_CAP


def daily_shuffle_enabled() -> bool:
    """Master switch for the seeded daily organic shuffle (plan §2.2).

    Defaults ON so category pages rotate fairly day-to-day. Set
    ``RANKING_DAILY_SHUFFLE=0`` to instantly revert to the legacy
    rating-sorted order (the safety valve for the rollout)."""
    raw = _env("RANKING_DAILY_SHUFFLE")
    if not raw:
        return True
    return raw.lower() in _TRUE


# --------------------------------------------------------------------------- #
# Sellable catalog (labels/blurbs only — prices are DATA in placement_prices).
# Mirrors the merchant-facing PURCHASABLE_TYPES so the storefront and the buy
# form describe the same products. Default prices below are a one-time seed the
# operator can load; the live price is always whatever the price book holds.
# --------------------------------------------------------------------------- #

# (placement_type, rank_tier) -> default price in cents, for the optional seed.
# Numbers track docs/monetization-research.md; the operator edits them in admin.
DEFAULT_PRICE_BOOK: dict[tuple[str, int | None], int] = {
    ("homepage_rotating", None): 9900,   # "share of home" rotating unit
    ("page_ad", None): 7900,             # one ad at the top of a category page
    ("category_rank", 1): 17900,         # #1 sticky tier
    ("category_rank", 2): 15900,
    ("category_rank", 3): 13900,
    ("category_rank", 4): 12900,
    ("category_rank", 5): 11900,
}

# Public storefront catalog (the three self-serve products), label + blurb.
STOREFRONT_OFFERS: tuple[dict, ...] = (
    {
        "key": "category_rank",
        "rank_tier": 1,
        "label": "Category top spot",
        "blurb": "Pin your business to the top of its category page, clearly "
        "labeled Sponsored. Up to three spots per category.",
    },
    {
        "key": "page_ad",
        "rank_tier": None,
        "label": "Category page ad",
        "blurb": "The single labeled ad unit at the top of a category page.",
    },
    {
        "key": "homepage_rotating",
        "rank_tier": None,
        "label": "Home rotating spot",
        "blurb": "A share of the home page rotation — one advertiser shown per "
        "visit, cycling across the pool.",
    },
)


def storefront_offers(db) -> list[dict]:
    """The public rate card: each product with a display price.

    Uses the live, admin-editable price book first
    (:func:`app.monetization.serving.price_for`); falls back to
    :data:`DEFAULT_PRICE_BOOK` (still config, never a template literal) as an
    indicative "starting at" price when the operator hasn't seeded the book yet.
    ``price_cents`` is ``None`` only when neither source has a number — the
    template then shows "Price on request" rather than inventing one.
    """
    from app.monetization.serving import price_for

    offers: list[dict] = []
    for o in STOREFRONT_OFFERS:
        live = None
        try:
            live = price_for(db, o["key"], rank_tier=o["rank_tier"])
        except Exception:  # noqa: BLE001 — a price lookup must never 500 the page
            live = None
        indicative = live is None
        price = live if live is not None else DEFAULT_PRICE_BOOK.get((o["key"], o["rank_tier"]))
        offers.append({**o, "price_cents": price, "indicative": indicative})
    return offers
