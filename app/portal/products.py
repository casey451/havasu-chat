"""Ad-product catalog for the business portal (Phase 2 §5b).

Prices are the monetization-model ranges, used as defaults (an admin can refine
them later). Scarcity is the pricing model: slot-backed exclusive products show
**live** availability computed from the active-sponsor count, so a sold-out
surface offers a waitlist, never a second slot. Nothing here is fabricated — the
availability for capped slots is a real query; uncapped products say so plainly.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AdSlot, Sponsor
from app.home.sponsor_store import _live_filter_for_slot

# (key, name, price range, blurb, backing AdSlot | None, cap | None)
# cap=None  -> uncapped (per-listing / per-event): always available.
# cap=int   -> exclusive surface: availability = cap - live active count.
_PRODUCTS: tuple[dict[str, Any], ...] = (
    {
        "key": "enriched",
        "name": "Verified & Enriched Listing",
        "price": "$39 / mo",
        "price_note": "founding rate · $390/yr",
        "blurb": "Claim your listing, then add photos, hours, menu and links — and wear the verified mark.",
        "slot": None,
        "cap": None,
        "cta": "/portal/claim",
        "cta_label": "Claim your listing",
    },
    {
        "key": "category",
        "name": "Category Sponsorship",
        "price": "$129–179 / mo",
        "price_note": "founding rate, 12-mo lock · premium categories (Eat & Drink, On the Water, Lodging, Home Services) $179",
        "blurb": "Own your category: one clearly-labeled spot pinned atop a category page. Exclusive — one per category.",
        "slot": AdSlot.SPOTLIGHT,
        "cap": None,  # per-category cap; shown as a note rather than a global count
        "note": "1 slot per category",
        "cta": "/portal/reserve?product=category",
        "cta_label": "Reserve this spot",
    },
    {
        "key": "featured",
        "name": "Homepage / Mode Featured",
        "price": "$99–199 / mo",
        "price_note": "founding rate · marquee $199, spotlight $99",
        "blurb": "A featured card on the home page or a mode landing (Lake / Night / Family).",
        "slot": AdSlot.PROMOTED,
        "cap": None,
        "note": "Few slots — limited",
        "cta": "/portal/reserve?product=featured",
        "cta_label": "Reserve this spot",
    },
    {
        "key": "event",
        "name": "Event Boost",
        "price": "$19 / event",
        "price_note": "or $49 / mo unlimited",
        "blurb": "Lift your event in the month calendar and the Today module for its run.",
        "slot": None,
        "cap": None,
        "cta": "/portal/reserve?product=event",
        "cta_label": "Reserve this spot",
    },
    {
        "key": "gas",
        "name": "Gas / Utility Sponsor",
        "price": "$149 / mo",
        "price_note": "founding rate",
        "blurb": "The single exclusive sponsor on the high-traffic gas page.",
        "slot": AdSlot.MARQUEE,
        "cap": 1,
        "cta": "/portal/reserve?product=gas",
        "cta_label": "Reserve this spot",
    },
    {
        "key": "founding",
        "name": "Founding Partner",
        "price": "$149 / mo",
        "price_note": "10 founding spots · 12-mo lock",
        "blurb": "The launch bundle: the Verified & Enriched Listing + homepage spotlight rotation + 2 event boosts a month + first dibs on your category sponsorship.",
        "slot": None,
        "cap": None,
        "note": "10 founding spots",
        "cta": "/portal/reserve?product=founding",
        "cta_label": "Reserve this spot",
    },
)


def get(key: str) -> dict[str, Any] | None:
    """Return the raw catalog entry for ``key`` (no live availability), or None.

    Used by the reservation flow to render a product summary (name/price) and
    snapshot the product name onto the reservation. Strips the internal
    ``slot``/``cap`` fields the public surface never needs.
    """
    for p in _PRODUCTS:
        if p["key"] == key:
            return {k: v for k, v in p.items() if k not in ("slot", "cap")}
    return None


def _availability(db: Session, slot: AdSlot | None, cap: int | None, note: str | None) -> dict[str, Any]:
    """Live availability for a product. Capped slots query the real active count."""
    if cap is None:
        return {"label": note or "Available", "sold_out": False, "scarce": bool(note)}
    active = _live_filter_for_slot(db.query(Sponsor), slot).count() if slot else 0
    remaining = max(0, cap - active)
    if remaining == 0:
        return {"label": "Sold out · join the waitlist", "sold_out": True, "scarce": True}
    return {"label": f"{remaining} of {cap} available", "sold_out": False, "scarce": True}


def catalog(db: Session) -> list[dict[str, Any]]:
    """The ad catalog with live availability for exclusive slots."""
    out: list[dict[str, Any]] = []
    for p in _PRODUCTS:
        out.append(
            {
                **{k: v for k, v in p.items() if k not in ("slot", "cap")},
                "availability": _availability(db, p.get("slot"), p.get("cap"), p.get("note")),
            }
        )
    return out
