"""Program price display (Step 3).

Single source of truth for turning a program's price into a short display
string. Price "lives on offerings" (the structured ``Offering`` rows on the
program's entity), so we prefer that; we fall back to the program's freeform
``cost`` text, and return ``""`` when neither is present (the caller renders
nothing rather than a fabricated price).

Why display-only (no facet): a *price facet* needs structured, range-filterable
price -- ``Offering.price_min_cents`` -- which is currently unpopulated
(``price_text`` is freeform and ``Program.cost`` is a string like "$15/class" /
"varies" / "Free"). Until a structured-price backfill lands, a facet would have
nothing to filter on, so it is deferred. This helper is built offering-first so
the display upgrades automatically once that data exists.
"""

from __future__ import annotations

from typing import Protocol


class _OfferingLike(Protocol):
    price_text: str | None
    price_min_cents: int | None
    price_max_cents: int | None


def _dollars(cents: int) -> str:
    """Whole dollars when even, else one decimal. 1500 -> '$15', 1599 -> '$15.99'."""
    if cents % 100 == 0:
        return f"${cents // 100}"
    return f"${cents / 100:.2f}"


def format_offering_price(offering: _OfferingLike | None) -> str:
    """Structured price string from an ``Offering``, or ``""``.

    Prefers the human ``price_text``; otherwise formats a cents range/point.
    """
    if offering is None:
        return ""
    text = (getattr(offering, "price_text", None) or "").strip()
    if text:
        return text
    lo = getattr(offering, "price_min_cents", None)
    hi = getattr(offering, "price_max_cents", None)
    if lo is not None and hi is not None and hi != lo:
        return f"{_dollars(lo)}-{_dollars(hi)}"
    if lo is not None:
        return _dollars(lo)
    if hi is not None:
        return _dollars(hi)
    return ""


def format_program_price(
    program_cost: str | None,
    offering: _OfferingLike | None = None,
) -> str:
    """Display string for a program's price.

    Offering price wins (price lives on offerings); falls back to the program's
    freeform ``cost``; ``""`` when neither is present -- never fabricated.
    """
    offering_price = format_offering_price(offering)
    if offering_price:
        return offering_price
    return (program_cost or "").strip()
