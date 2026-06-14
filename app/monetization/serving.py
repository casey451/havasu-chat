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

import random
from collections.abc import Sequence
from dataclasses import dataclass


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
