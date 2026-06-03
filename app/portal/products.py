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
        "price": "$20–50 / mo",
        "blurb": "Claim your listing, then add photos, hours, menu and links — and wear the verified mark.",
        "slot": None,
        "cap": None,
        "cta": "/portal/claim",
        "cta_label": "Claim your listing",
    },
    {
        "key": "category",
        "name": "Category Sponsorship",
        "price": "$75–250 / mo",
        "blurb": "One clearly-labeled spot pinned atop a category page (e.g. Eat & Drink). One per category.",
        "slot": AdSlot.SPOTLIGHT,
        "cap": None,  # per-category cap; shown as a note rather than a global count
        "note": "1 slot per category",
        "cta": "/contribute",
        "cta_label": "Enquire",
    },
    {
        "key": "featured",
        "name": "Homepage / Mode Featured",
        "price": "$150–400 / mo",
        "blurb": "A featured card on the home page or a mode landing (Lake / Night / Family).",
        "slot": AdSlot.PROMOTED,
        "cap": None,
        "note": "Few slots — limited",
        "cta": "/contribute",
        "cta_label": "Enquire",
    },
    {
        "key": "event",
        "name": "Event Boost",
        "price": "$25–100 / event",
        "blurb": "Lift your event in the month calendar and the Today module for its run.",
        "slot": None,
        "cap": None,
        "cta": "/contribute",
        "cta_label": "Enquire",
    },
    {
        "key": "gas",
        "name": "Gas / Utility Sponsor",
        "price": "$100–300 / mo",
        "blurb": "The single exclusive sponsor on the high-traffic gas page.",
        "slot": AdSlot.MARQUEE,
        "cap": 1,
        "cta": "/contribute",
        "cta_label": "Enquire",
    },
)


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
