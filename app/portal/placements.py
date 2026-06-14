"""Merchant-facing placement purchase logic (Phase F §8).

Ownership runs through a *verified* :class:`~app.db.models.Claim` — the same
bridge the provider profile uses for ``viewer_is_owner``. A merchant can only buy
placements for a provider whose entity they've verifiably claimed.

A purchase creates a :class:`~app.db.monetization_models.Placement` in the
``pending`` status (awaiting payment / operator approval). No money moves here —
Stripe checkout is a later increment; until then the operator confirms and
invoices, mirroring the existing ad-reservation flow. ``pending`` placements are
NOT served (serving reads ``status == "active"`` only), so creating one has zero
effect on the live site until it's activated.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Claim, Provider
from app.db.monetization_models import (
    AdCreative,
    BillingType,
    Placement,
    PlacementStatus,
    PlacementType,
)
from app.monetization import serving

# Placement types a merchant can self-purchase, with the inputs each one needs.
PURCHASABLE_TYPES: dict[str, dict] = {
    PlacementType.homepage_rotating.value: {
        "label": "Homepage rotating spot",
        "needs_category": False,
        "needs_tier": False,
        "blurb": "Your business in the homepage rotation — one shown per visit.",
    },
    PlacementType.category_rank.value: {
        "label": "Category top ranking",
        "needs_category": True,
        "needs_tier": True,
        "blurb": "A sticky tier (1–5) at the top of a category page. #1 is locked first.",
    },
    PlacementType.page_ad.value: {
        "label": "Category page ad",
        "needs_category": True,
        "needs_tier": False,
        "blurb": "The single labeled ad slot on a category/niche page.",
    },
}

VALID_BILLING = {BillingType.monthly.value, BillingType.recurring.value}


def claimed_providers(db: Session, user_id: str) -> list[Provider]:
    """Providers whose entity this user has a VERIFIED claim on (their listings)."""
    return list(
        db.scalars(
            select(Provider)
            .join(Claim, Claim.entity_id == Provider.entity_id)
            .where(Claim.user_id == user_id, Claim.status == "verified")
            .order_by(Provider.provider_name)
        ).all()
    )


def owns_provider(db: Session, user_id: str, provider_id: str) -> bool:
    """True iff ``user_id`` holds a verified claim on ``provider_id``'s entity."""
    provider = db.get(Provider, provider_id)
    if provider is None:
        return False
    claim = (
        db.query(Claim)
        .filter(
            Claim.user_id == user_id,
            Claim.entity_id == provider.entity_id,
            Claim.status == "verified",
        )
        .first()
    )
    return claim is not None


def active_placements_for_providers(db: Session, provider_ids: list[str]) -> list[Placement]:
    """Current (non-released, non-expired) placements held by these providers,
    for the dashboard — includes ``pending`` so a merchant sees a purchase they
    just made awaiting confirmation."""
    if not provider_ids:
        return []
    return list(
        db.scalars(
            select(Placement)
            .where(
                Placement.provider_id.in_(provider_ids),
                Placement.status.in_(
                    [PlacementStatus.pending.value, PlacementStatus.active.value]
                ),
            )
            .order_by(Placement.created_at.desc())
        ).all()
    )


def validate_purchase(
    placement_type: str,
    *,
    category_slug: str | None,
    rank_tier: int | None,
    billing_type: str,
) -> dict[str, str]:
    """Return a field→message error dict ({} when valid) for a purchase request."""
    errors: dict[str, str] = {}
    spec = PURCHASABLE_TYPES.get(placement_type)
    if spec is None:
        errors["placement_type"] = "Pick a placement type."
        return errors  # nothing else is meaningful without a valid type

    if spec["needs_category"] and not category_slug:
        errors["category_slug"] = "Pick the category page this applies to."
    if spec["needs_tier"]:
        if rank_tier is None or not (1 <= rank_tier <= 5):
            errors["rank_tier"] = "Pick a tier from 1 to 5."
    if billing_type not in VALID_BILLING:
        errors["billing_type"] = "Choose monthly or recurring."
    return errors


def creatives_for_provider(db: Session, provider_id: str) -> list[AdCreative]:
    """Active ad creatives belonging to a provider (newest first)."""
    return list(
        db.scalars(
            select(AdCreative)
            .where(AdCreative.provider_id == provider_id, AdCreative.active.is_(True))
            .order_by(AdCreative.created_at.desc())
        ).all()
    )


def create_creative(
    db: Session,
    *,
    provider_id: str,
    headline: str | None,
    body: str | None,
    cta_label: str | None,
    cta_url: str | None,
    image_url: str | None,
    image_url_mobile: str | None,
) -> AdCreative:
    """Create a URL-based ad creative for a provider. Caller checks ownership."""
    creative = AdCreative(
        provider_id=provider_id,
        headline=(headline or None),
        body=(body or None),
        cta_label=(cta_label or None),
        cta_url=(cta_url or None),
        image_url=(image_url or None),
        image_url_mobile=(image_url_mobile or None),
        active=True,
    )
    db.add(creative)
    db.commit()
    db.refresh(creative)
    return creative


def create_pending_placement(
    db: Session,
    *,
    provider_id: str,
    placement_type: str,
    category_slug: str | None,
    rank_tier: int | None,
    billing_type: str,
    creative_id: str | None = None,
) -> Placement:
    """Create a ``pending`` Placement, pricing it from the live price book.

    Caller MUST have checked :func:`owns_provider` and :func:`validate_purchase`
    first. A missing price defaults ``price_cents`` to 0 — the operator sets the
    real figure on confirmation rather than the merchant being blocked. A
    ``creative_id`` is attached only when it belongs to the same provider (a
    mismatched/foreign id is ignored rather than trusted).
    """
    spec = PURCHASABLE_TYPES[placement_type]
    cat = category_slug if spec["needs_category"] else None
    tier = rank_tier if spec["needs_tier"] else None
    price_cents = serving.price_for(
        db, placement_type, category_slug=cat, rank_tier=tier
    ) or 0

    safe_creative_id: str | None = None
    if creative_id:
        creative = db.get(AdCreative, creative_id)
        if creative is not None and creative.provider_id == provider_id:
            safe_creative_id = creative.id

    placement = Placement(
        provider_id=provider_id,
        placement_type=placement_type,
        category_slug=cat,
        rank_tier=tier,
        billing_type=billing_type,
        price_cents=price_cents,
        status=PlacementStatus.pending.value,
        creative_id=safe_creative_id,
    )
    db.add(placement)
    db.commit()
    db.refresh(placement)
    return placement
