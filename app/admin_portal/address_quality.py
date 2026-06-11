"""Address-quality flag queue (WS-4, Track B2) — pattern-check, never auto-fix.

Flags are computed LIVE from current Location rows joined to their active
Provider (same always-fresh approach as the dedupe pair queue): the
mechanical shapes (city-repeat, comma runs, empty) plus the judgment shape —
no leading street number, which is OFTEN legitimate (parks, trails, areas,
service-area businesses). That's exactly why this is a review queue and not a
script: a human marks the legit ones OK and fixes the real ones on the
existing provider tools.

Dismissals persist on ``Provider.attributes["address_flag_dismissed"]`` (the
operator-curated JSON bag) so a reviewed row stays out of the queue without a
schema change. The mechanical shapes are normally drained by
``scripts/fix_address_quality.py`` first; whatever it refuses lands here.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.admin_portal.audit_models import record_audit
from app.admin_portal.guard import guard
from app.admin_portal.shared import render
from app.db.database import get_db
from app.db.models import Location, Provider

router = APIRouter()

_DISMISS_KEY = "address_flag_dismissed"
_MAX_ROWS = 400  # rendering cap; counts stay exact


@dataclass(frozen=True)
class AddressFlag:
    provider_id: str
    provider_name: str
    slug: str | None
    location_id: int
    address: str
    flags: tuple[str, ...]


def _flags_for(address: str | None) -> tuple[str, ...]:
    from app.core.address import count_city_mentions

    if address is None or not address.strip():
        return ("empty",)
    out: list[str] = []
    # CITY-SHAPED counting (see app.core.address.count_city_mentions): streets
    # named Lake Havasu Ave and venue names like "Lake Havasu State Park" are
    # not city repeats — the 2026-06-10 prod run proved bare substring
    # counting floods this queue with ~268 false positives.
    if count_city_mentions(address) >= 2:
        out.append("city_repeat")
    if ",," in address.replace(", ", ",") or "  " in address:
        out.append("comma_or_space_run")
    if not address.strip()[0].isdigit():
        out.append("no_street_number")
    return tuple(out)


def address_flag_rows(db: Session) -> list[AddressFlag]:
    """Flagged (location, provider) rows for active, non-draft providers."""
    rows = (
        db.query(Location, Provider)
        .join(Provider, Provider.entity_id == Location.entity_id)
        .filter(Provider.is_active.is_(True), Provider.draft.is_(False))
        .all()
    )
    out: list[AddressFlag] = []
    for loc, prov in rows:
        if (prov.attributes or {}).get(_DISMISS_KEY):
            continue
        flags = _flags_for(loc.address)
        if not flags:
            continue
        out.append(
            AddressFlag(
                provider_id=prov.id,
                provider_name=prov.provider_name or "(unnamed)",
                slug=prov.slug,
                location_id=loc.id,
                address=loc.address or "",
                flags=flags,
            )
        )
    # Mechanical shapes first (script leftovers — highest fix value), then the
    # judgment pile, alphabetical inside each band for a stable worklist.
    out.sort(key=lambda f: ("no_street_number" in f.flags and len(f.flags) == 1,
                            f.provider_name.lower()))
    return out


def address_flag_count(db: Session) -> int:
    """Count for the dashboard queue card."""
    return len(address_flag_rows(db))


@router.get("/addresses", response_model=None)
def addresses_page(
    request: Request, db: Session = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    if (redirect := guard(request)) is not None:
        return redirect
    rows = address_flag_rows(db)
    return render(
        request,
        "portal_addresses.html",
        "addresses",
        {"rows": rows[:_MAX_ROWS], "total": len(rows), "capped": len(rows) > _MAX_ROWS},
    )


@router.post("/addresses/{provider_id}/dismiss", response_model=None)
def dismiss_address_flag(
    provider_id: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse | HTMLResponse:
    """Mark a flagged address as legitimate (parks/trails/service-area)."""
    if (redirect := guard(request)) is not None:
        return redirect
    prov = db.get(Provider, provider_id)
    if prov is None:
        return HTMLResponse("<p>Provider not found.</p>", status_code=404)
    attrs = dict(prov.attributes or {})
    attrs[_DISMISS_KEY] = True
    prov.attributes = attrs
    record_audit(
        db,
        action="address_flag_dismissed",
        target_type="provider",
        target_id=provider_id,
        detail=(prov.address or "")[:200],
    )
    db.commit()
    return RedirectResponse(url="/admin/portal/addresses", status_code=303)
