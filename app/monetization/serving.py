"""Phase F (§7.1 + §7.2) — placement serving: sticky-tier category ranking and
homepage rotation.

The ranking math is pure (deterministic with an injected ``rng``) so it is
unit-testable without a database. Thin DB-backed helpers fetch the active
placement rows and hand off to the pure functions.

§7.2 sticky-tier guarantees:
  * tier 1 → ALWAYS position 1 (locked).
  * tier t (2..5) → guaranteed somewhere in the top ``t`` (floats within band).
  * every remaining top-5 slot + everything below = unpaid listings, shuffled.

§7.1 homepage block: one business drawn from the rotating pool per page load.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class RankedItem:
    """One row in a category result — a paid placement or an organic listing."""

    key: str               # provider_id (or any stable identifier)
    paid_tier: int | None  # 1..5 for a category_rank placement, else None


def arrange_top5(
    sold_by_tier: dict[int, str],
    unpaid_keys: Sequence[str],
    rng: random.Random | None = None,
) -> list[RankedItem]:
    """Order a category's listings per §7.2.

    ``sold_by_tier`` maps a rank tier (1..5) to the provider_id holding it.
    ``unpaid_keys`` are the organic provider_ids in any order. Returns the full
    ordered list (paid top section first, then shuffled remainder).
    """
    rng = rng or random.Random()
    slots: list[str | None] = [None] * 5
    tiers = {t: pid for t, pid in sold_by_tier.items() if 1 <= t <= 5}

    # Tier 1 is locked to position 1; tiers 2..5 float in a random open slot
    # within their band (positions 1..t), guaranteeing "at least tier-t standing".
    if 1 in tiers:
        slots[0] = tiers[1]
    for t in range(2, 6):
        if t not in tiers:
            continue
        open_within = [i for i in range(t) if slots[i] is None]
        if not open_within:  # band already full (oversold) — spill to any open top-5 slot
            open_within = [i for i in range(5) if slots[i] is None]
        if open_within:
            slots[rng.choice(open_within)] = tiers[t]

    paid_ids = set(tiers.values())
    pool = [k for k in unpaid_keys if k not in paid_ids]
    rng.shuffle(pool)

    tier_by_id = {pid: t for t, pid in tiers.items()}
    for i in range(5):
        if slots[i] is None and pool:
            slots[i] = pool.pop()

    out = [RankedItem(s, tier_by_id.get(s)) for s in slots if s is not None]
    out.extend(RankedItem(k, None) for k in pool)
    return out


def pick_homepage(pool_keys: Sequence[str], rng: random.Random | None = None) -> str | None:
    """§7.1 — one business from the rotating homepage pool (per page load)."""
    keys = list(pool_keys)
    if not keys:
        return None
    return (rng or random.Random()).choice(keys)


def apply_category_order(
    ordered_keys: Sequence[str],
    sold_by_tier: dict[int, str],
    rng: random.Random | None = None,
) -> list[str]:
    """Overlay sticky-tier placements onto an already-ordered category list.

    Unlike :func:`arrange_top5` (which shuffles the unpaid pool), this PRESERVES
    the caller's organic order for unpaid listings — so the user's chosen sort
    (top-rated / closest / editorial) still holds below the paid spots. Paid
    tiers are pinned into the top-5 per §7.2 (tier 1 locked at #1; tiers 2-5
    float within their band). Returns the reordered key list.

    Dormant by design: with no sold tiers (the current state — nothing sold until
    the portal exists), the input order is returned unchanged.
    """
    keyset = set(ordered_keys)
    tiers = {t: pid for t, pid in sold_by_tier.items() if 1 <= t <= 5 and pid in keyset}
    if not tiers:
        return list(ordered_keys)

    rng = rng or random.Random()
    slots: list[str | None] = [None] * 5
    if 1 in tiers:
        slots[0] = tiers[1]
    for t in range(2, 6):
        if t not in tiers:
            continue
        open_within = [i for i in range(t) if slots[i] is None]
        if not open_within:
            open_within = [i for i in range(5) if slots[i] is None]
        if open_within:
            slots[rng.choice(open_within)] = tiers[t]

    paid = set(tiers.values())
    rest = [k for k in ordered_keys if k not in paid]  # organic order kept
    for i in range(5):
        if slots[i] is None and rest:
            slots[i] = rest.pop(0)
    return [s for s in slots if s is not None] + rest


# --------------------------------------------------------------------------- #
# §2.2 — the non-paid ranking: a seeded DAILY deterministic shuffle, gated at a
# config rating threshold, with no-review businesses in a labeled tail (not
# excluded). Pure + deterministic so it is unit-testable without a DB or a clock.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ItemRating:
    """A listing's identity + the two signals the gate reads."""

    key: str                  # provider_id (stable identifier)
    rating: float | None      # google_rating (None / no reviews → the new tail)
    review_count: int | None  # google_review_count


@dataclass(frozen=True)
class Arranged:
    """The result of :func:`arrange_listing` — an order plus the labeling sets."""

    order: list[str]             # final key order (paid pinned per the cap)
    new_unrated: frozenset[str]  # keys to label "New / Not yet rated" (the tail)
    sponsored: frozenset[str]    # paid-tier holders present (labeled, any slot)


def listing_day(now: datetime | None) -> str:
    """The shuffle's day bucket (``YYYY-MM-DD``) in Lake Havasu local time.

    The seed rotates on this string, so the order is stable within a local day
    (cacheable, shareable, consistent on revisit) and reshuffles across days.
    """
    from app.core.timezone import LAKE_HAVASU_TZ

    dt = now or datetime.now(LAKE_HAVASU_TZ)
    if dt.tzinfo is not None:
        dt = dt.astimezone(LAKE_HAVASU_TZ)
    return dt.date().isoformat()


def daily_seed(category_slug: str, day: str, salt: str = "") -> int:
    """A deterministic PRNG seed from (category, day[, salt]) — §2.2."""
    digest = hashlib.sha256(f"{category_slug}|{day}|{salt}".encode()).hexdigest()
    return int(digest[:16], 16)


def _seeded_shuffle(keys: Sequence[str], category_slug: str, day: str, salt: str) -> list[str]:
    out = list(keys)
    random.Random(daily_seed(category_slug, day, salt)).shuffle(out)  # Fisher-Yates
    return out


def partition_by_rating(
    items: Sequence[ItemRating], threshold: float
) -> tuple[list[str], list[str], list[str]]:
    """Split keys into (rated>threshold, new/unrated, rated≤threshold).

    A business with no reviews (``review_count`` falsy or ``rating`` None) is
    "new/unrated" — it goes in the labeled tail, never excluded. A reviewed
    business above the gate is in the quality pool; one at/below it sinks to the
    low band (still shown, below the tail).
    """
    rated: list[str] = []
    new_unrated: list[str] = []
    low: list[str] = []
    for it in items:
        if not (it.review_count or 0) or it.rating is None:
            new_unrated.append(it.key)
        elif it.rating > threshold:
            rated.append(it.key)
        else:
            low.append(it.key)
    return rated, new_unrated, low


def arrange_listing(
    items: Sequence[ItemRating],
    sold_by_tier: dict[int, str],
    *,
    category_slug: str,
    day: str,
    threshold: float,
    cap: int,
    shuffle: bool = True,
) -> Arranged:
    """Order one category/leaf listing per the brief: ≤``cap`` paid cards pinned
    above the fold, then a daily-shuffled >``threshold`` quality pool, then the
    daily-shuffled reviewed-but-≤``threshold`` low band, then the daily-shuffled
    "New / Not yet rated" tail at the very bottom.

    ``items`` arrives in the caller's organic order (rating-sorted). With
    ``shuffle=False`` (the rollback switch) that order is preserved and only the
    paid pinning + cap apply, so the page falls back to the legacy ranking.

    Paid pinning honours the §2.1 cap: only tiers ``1..cap`` are pinned above the
    first organic result; a sold tier beyond the cap stays in ``sponsored`` (still
    labeled) but flows with the organic order rather than reading "all ads."
    """
    present = {it.key for it in items}
    sponsored = frozenset(pid for pid in sold_by_tier.values() if pid in present)

    if shuffle:
        rated, new_unrated, low = partition_by_rating(items, threshold)
        # Order: the >gate quality pool, then the reviewed-but-below-gate band,
        # then the "New / Not yet rated" tail at the very bottom (its own labeled
        # section) — every band Fisher-Yates'd with a distinct daily seed.
        organic = (
            _seeded_shuffle(rated, category_slug, day, "rated")
            + _seeded_shuffle(low, category_slug, day, "low")
            + _seeded_shuffle(new_unrated, category_slug, day, "new")
        )
        # A paid holder is never labeled "new" — the badge would contradict it.
        tail = frozenset(k for k in new_unrated if k not in sponsored)
    else:
        organic = [it.key for it in items]
        tail = frozenset()

    pin_tiers = {t: pid for t, pid in sold_by_tier.items() if 1 <= t <= cap}
    # Stable per-day tier float (so a tier-2..cap holder doesn't jump per request).
    rng = random.Random(daily_seed(category_slug, day, "pin"))
    order = apply_category_order(organic, pin_tiers, rng=rng)
    return Arranged(order=order, new_unrated=tail, sponsored=sponsored)


# --------------------------------------------------------------------------- #
# DB-backed helpers (fetch active placements, then delegate to the pure funcs).
# --------------------------------------------------------------------------- #


def price_for(
    db,
    placement_type: str,
    *,
    category_slug: str | None = None,
    rank_tier: int | None = None,
) -> int | None:
    """Look up the price (cents) for a placement from the ``placement_prices``
    book, most-specific first with graceful fallback to the global defaults:

        (type, category_slug, rank_tier)  →  (type, category_slug, NULL)
        →  (type, NULL, rank_tier)         →  (type, NULL, NULL)

    Returns the first *active* match's ``price_cents``, or ``None`` if the book
    has no applicable row (the portal then shows "price on request" rather than
    inventing a number). Only the global-default rows ship seeded; per-category
    overrides are added by the admin later and win automatically here.
    """
    from sqlalchemy import select

    from app.db.monetization_models import PlacementPrice

    seen: set[tuple[str | None, int | None]] = set()
    for cat, tier in (
        (category_slug, rank_tier),
        (category_slug, None),
        (None, rank_tier),
        (None, None),
    ):
        if (cat, tier) in seen:
            continue
        seen.add((cat, tier))
        row = db.scalars(
            select(PlacementPrice).where(
                PlacementPrice.placement_type == placement_type,
                PlacementPrice.category_slug.is_(None)
                if cat is None
                else PlacementPrice.category_slug == cat,
                PlacementPrice.rank_tier.is_(None)
                if tier is None
                else PlacementPrice.rank_tier == tier,
                PlacementPrice.active.is_(True),
            )
        ).first()
        if row is not None:
            return row.price_cents
    return None


def active_category_tiers(db, category_slug: str) -> dict[int, str]:
    """Active category_rank tiers for a category, {tier: provider_id}. If a tier
    is somehow held twice, the earliest-created holder wins (deterministic)."""
    from sqlalchemy import select

    from app.db.monetization_models import Placement, PlacementStatus, PlacementType

    rows = db.scalars(
        select(Placement).where(
            Placement.placement_type == PlacementType.category_rank.value,
            Placement.category_slug == category_slug,
            Placement.status == PlacementStatus.active.value,
            Placement.rank_tier.is_not(None),
        )
    ).all()
    out: dict[int, str] = {}
    for p in sorted(rows, key=lambda r: r.created_at):
        out.setdefault(int(p.rank_tier), p.provider_id)
    return out


def active_category_creatives(db, category_slug: str) -> dict[str, dict[str, str]]:
    """Per-provider ad creative for active ``category_rank`` placements on
    ``category_slug`` that carry an attached, provider-owned creative.

    Returns ``{provider_id: {"image_url": ..., "headline": ...}}`` — only the
    keys the creative actually sets — so a category/leaf card can render the
    paid creative's art/headline instead of the listing's own photo/name. The
    creative must belong to the same provider (the honesty rule
    ``Placement.creative_id`` already enforces at purchase) and be ``active``;
    a mismatched or inactive creative is ignored.

    Dormant by design: the empty default (nothing sold, or no active placement
    carries a creative) leaves every surface rendering today's organic card. If
    a provider somehow holds two creative-bearing placements on one slug, the
    earliest-created wins (same determinism as :func:`active_category_tiers`).
    """
    from sqlalchemy import select

    from app.db.monetization_models import (
        AdCreative,
        Placement,
        PlacementStatus,
        PlacementType,
    )

    rows = db.scalars(
        select(Placement).where(
            Placement.placement_type == PlacementType.category_rank.value,
            Placement.category_slug == category_slug,
            Placement.status == PlacementStatus.active.value,
            Placement.creative_id.is_not(None),
        )
    ).all()
    out: dict[str, dict[str, str]] = {}
    for p in sorted(rows, key=lambda r: r.created_at):
        if p.provider_id in out:
            continue
        creative = db.get(AdCreative, p.creative_id)
        if creative is None or not creative.active:
            continue
        if creative.provider_id != p.provider_id:
            continue  # only a creative the provider actually owns
        data: dict[str, str] = {}
        if creative.image_url:
            data["image_url"] = creative.image_url
        if creative.headline:
            data["headline"] = creative.headline
        if data:
            out[p.provider_id] = data
    return out


def active_homepage_pool(db) -> list[str]:
    """Provider ids in the active homepage rotating pool (§7.1)."""
    from sqlalchemy import select

    from app.db.monetization_models import Placement, PlacementStatus, PlacementType

    return list(
        db.scalars(
            select(Placement.provider_id).where(
                Placement.placement_type == PlacementType.homepage_rotating.value,
                Placement.status == PlacementStatus.active.value,
            )
        ).all()
    )


def serve_homepage_placement(db) -> dict | None:
    """§7.1 — one business from the active homepage rotating pool, shaped as the
    home marquee dict (the same keys ``active_marquee`` returns).

    Returns ``None`` when the pool is empty — the dormant default today — so the
    caller falls back to the legacy sponsor marquee and, failing that, the unsold
    claim line. A placement marquee carries ``click_url`` (the provider profile)
    so the template links straight to the listing instead of the Sponsor-only
    ``/sponsor/click`` route; it also carries the honest ``Sponsored`` framing via
    the marquee's existing ``Featured`` tag.
    """
    pid = pick_homepage(active_homepage_pool(db))
    if pid is None:
        return None

    from sqlalchemy import select

    from app.analytics import record_event
    from app.db.models import Provider
    from app.db.monetization_models import AdCreative, Placement, PlacementStatus, PlacementType
    from app.providers.queries import derive_hero_photo

    provider = db.get(Provider, pid)
    if provider is None or not provider.slug:
        return None

    profile_url = f"/provider/{provider.slug}"
    headline = provider.provider_name
    pitch = (provider.featured_description or provider.description or "").strip()
    if len(pitch) > 140:
        pitch = pitch[:139].rstrip() + "…"
    cta_label = "View listing"
    image_url = derive_hero_photo(provider)

    # Prefer an attached ad creative's copy/art when the active placement has one;
    # the click target stays the internal provider profile (open-redirect-safe).
    placement = db.scalars(
        select(Placement).where(
            Placement.provider_id == provider.id,
            Placement.placement_type == PlacementType.homepage_rotating.value,
            Placement.status == PlacementStatus.active.value,
        )
    ).first()
    if placement is not None and placement.creative_id:
        creative = db.get(AdCreative, placement.creative_id)
        if creative is not None:
            headline = creative.headline or headline
            pitch = creative.body or pitch
            cta_label = creative.cta_label or cta_label
            image_url = creative.image_url or image_url

    record_event(
        db,
        "home.marquee.impression",
        slot="marquee",
        provider_id=provider.id,
        payload={"source": "placement"},
    )
    return {
        "id": provider.id,
        "name": provider.provider_name,
        "headline": headline,
        "pitch": pitch,
        "eyebrow": "",
        "cta_label": cta_label,
        "cta_url": profile_url,
        "click_url": profile_url,
        "image_url": image_url,
        "is_placement": True,
    }


def active_page_ad_provider(db, category_slug: str) -> str | None:
    """Provider id holding the active ``page_ad`` placement for ``category_slug``.

    At most one ad serves a category page; if a slug somehow holds two, the
    earliest-created wins (same determinism as :func:`active_category_tiers`).
    Returns ``None`` when nothing is sold — the dormant default today.
    """
    from sqlalchemy import select

    from app.db.monetization_models import Placement, PlacementStatus, PlacementType

    rows = db.scalars(
        select(Placement).where(
            Placement.placement_type == PlacementType.page_ad.value,
            Placement.category_slug == category_slug,
            Placement.status == PlacementStatus.active.value,
        )
    ).all()
    if not rows:
        return None
    return sorted(rows, key=lambda r: r.created_at)[0].provider_id


def serve_category_page_ad(db, category_slug: str) -> dict | None:
    """§7 page_ad — the single paid ad near the top of a category page, shaped as
    the category ``sponsored`` dict (the same keys ``active_promoted`` returns,
    plus ``click_url`` and ``is_placement``).

    Returns ``None`` when no ``page_ad`` is sold for ``category_slug`` (the
    dormant default today) so the caller falls back to the legacy category
    sponsor and, failing that, renders no slot. An attached, provider-owned ad
    creative overrides the copy/art; the click target stays the internal provider
    profile (open-redirect-safe). The unit is rendered with the existing
    "Category sponsor" honesty label.
    """
    pid = active_page_ad_provider(db, category_slug)
    if pid is None:
        return None

    from sqlalchemy import select

    from app.analytics import record_event
    from app.db.models import Provider
    from app.db.monetization_models import AdCreative, Placement, PlacementStatus, PlacementType
    from app.providers.queries import derive_hero_photo

    provider = db.get(Provider, pid)
    if provider is None or not provider.slug:
        return None

    profile_url = f"/provider/{provider.slug}"
    headline = provider.provider_name
    pitch = (provider.featured_description or provider.description or "").strip()
    if len(pitch) > 140:
        pitch = pitch[:139].rstrip() + "…"
    image_url = derive_hero_photo(provider)

    placement = db.scalars(
        select(Placement)
        .where(
            Placement.provider_id == provider.id,
            Placement.placement_type == PlacementType.page_ad.value,
            Placement.category_slug == category_slug,
            Placement.status == PlacementStatus.active.value,
        )
        .order_by(Placement.created_at)  # earliest-created wins (determinism contract)
    ).first()
    if placement is not None and placement.creative_id:
        creative = db.get(AdCreative, placement.creative_id)
        if creative is not None and creative.active and creative.provider_id == provider.id:
            headline = creative.headline or headline
            pitch = creative.body or pitch
            image_url = creative.image_url or image_url

    record_event(
        db,
        "category.page_ad.impression",
        slot="page_ad",
        provider_id=provider.id,
        payload={"source": "placement", "category_slug": category_slug},
    )
    return {
        "id": provider.id,
        "name": provider.provider_name,
        "headline": headline,
        "pitch": pitch,
        "image_url": image_url,
        "click_url": profile_url,
        "is_placement": True,
    }


def _ordered_pool(db, exclude_ids: set[str]) -> list[tuple[Any, Any]]:
    """Active homepage-rotating providers, de-duped, DAILY-shuffled, skipping
    ``exclude_ids``. Returns ``[(Provider, Placement), …]``.

    Shared by the Tier-2 (featured) and Tier-3 (promoted) home slots so the same
    rotating pool feeds all three home units (marquee + featured + promoted) with
    DISTINCT businesses per load — the caller passes the ids already taken by the
    higher slots. The order is seeded on today's date (§2.2), so which ~10
    advertisers surface in the bounded slots rotates fairly day-to-day while
    staying stable within a day. Dormant by design: an empty pool yields ``[]``.
    """
    from sqlalchemy import select

    from app.db.models import Provider
    from app.db.monetization_models import Placement, PlacementStatus, PlacementType

    rows = list(
        db.scalars(
            select(Placement).where(
                Placement.placement_type == PlacementType.homepage_rotating.value,
                Placement.status == PlacementStatus.active.value,
            )
        ).all()
    )
    # Daily fair rotation: a stable created_at tiebreak first (determinism if two
    # rows share a second), then Fisher-Yates by today's seed.
    rows.sort(key=lambda r: (r.created_at, r.id))
    random.Random(daily_seed("__home__", listing_day(None))).shuffle(rows)
    seen = set(exclude_ids)
    out = []
    for p in rows:
        if p.provider_id in seen:
            continue
        seen.add(p.provider_id)
        provider = db.get(Provider, p.provider_id)
        if provider is not None and provider.slug:
            out.append((provider, p))
    return out


def serve_homepage_featured(db, *, exclude_ids: set[str], limit: int = 3) -> list[dict]:
    """§7.1 Tier-2 — up to ``limit`` businesses from the homepage rotating pool,
    shaped as the home "Featured this week" cards (the same keys
    :func:`app.home.sandstone.featured_cards` produces: ``empty``/``url``/
    ``image_url``/``eyebrow``/``name``/``deal``). The template renders the
    ``Sponsored`` label.

    Dormant by design: an empty pool (or one already drained by the marquee)
    returns ``[]`` so the caller falls back to the legacy spotlight cards.
    """
    from app.analytics import record_event
    from app.providers.queries import derive_hero_photo

    out: list[dict] = []
    for provider, _placement in _ordered_pool(db, exclude_ids)[:limit]:
        deal = (provider.featured_description or "").strip()
        if len(deal) > 90:
            deal = deal[:89].rstrip() + "…"
        out.append(
            {
                "id": provider.id,
                "empty": False,
                "url": f"/provider/{provider.slug}",
                "image_url": derive_hero_photo(provider),
                "eyebrow": "",
                "name": provider.provider_name,
                "deal": deal,
                "is_placement": True,
            }
        )
        record_event(
            db,
            "home.featured.impression",
            slot="featured",
            provider_id=provider.id,
            payload={"source": "placement"},
        )
    return out


def serve_homepage_promoted(db, *, exclude_ids: set[str]) -> dict | None:
    """§7.1 Tier-3 — one business from the homepage rotating pool, shaped as the
    home promoted in-feed card (``id``/``cta_url``/``click_url``/``image_url``/
    ``eyebrow``/``headline``/``pitch``/``cta_label``). An attached, provider-owned
    creative overrides the copy/art; the click target stays the provider profile.

    Dormant by design: an empty pool (or one drained by the marquee + featured)
    returns ``None`` so the caller falls back to the legacy promoted sponsor.
    """
    from app.analytics import record_event
    from app.db.monetization_models import AdCreative
    from app.providers.queries import derive_hero_photo

    pool = _ordered_pool(db, exclude_ids)
    if not pool:
        return None
    provider, placement = pool[0]
    profile_url = f"/provider/{provider.slug}"
    headline = provider.provider_name
    pitch = (provider.featured_description or provider.description or "").strip()
    if len(pitch) > 140:
        pitch = pitch[:139].rstrip() + "…"
    cta_label = "View listing"
    image_url = derive_hero_photo(provider)
    if placement.creative_id:
        creative = db.get(AdCreative, placement.creative_id)
        if creative is not None and creative.active and creative.provider_id == provider.id:
            headline = creative.headline or headline
            pitch = creative.body or pitch
            cta_label = creative.cta_label or cta_label
            image_url = creative.image_url or image_url
    record_event(
        db,
        "home.promoted.impression",
        slot="promoted",
        provider_id=provider.id,
        payload={"source": "placement"},
    )
    return {
        "id": provider.id,
        "cta_url": profile_url,
        "click_url": profile_url,
        "image_url": image_url,
        "eyebrow": "",
        "headline": headline,
        "pitch": pitch,
        "cta_label": cta_label,
        "is_placement": True,
    }
