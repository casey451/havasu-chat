"""GET /api/micro_ad — small sponsor payload for the chat loading overlay (Phase A4).

Surfaces a single live sponsor in the chat loading state so the otherwise-dead
"thinking" moment carries a lightweight house/sponsor message. Reads the same
live population the home page uses (slot + status=approved + active + within
booking window) but is intentionally a *read-only* lookup:

  IMPRESSION POLICY (deliberate): this endpoint does NOT bump
  ``Sponsor.impressions`` and does NOT emit a ``record_event`` impression row.
  The on-page counters and ``analytics_events`` describe paid /home surfaces;
  inflating them from a transient load-screen render that the user may never
  read would corrupt the CTR denominator advertisers rely on. If a future
  paid "loading micro-ad" tier is sold, give it its own counter/event name
  rather than reusing the home-tier impression population. (FLAG: whether the
  loading micro-ad is a new paid tier is a Casey product decision.)

Slot selection: defaults to the MARQUEE slot (the highest-value single-row
tier, already sold daily). The slot is configurable via the ``slot`` query
param so the surface can be repointed without a code change once Casey decides
what is sold here. Returns ``{"micro_ad": null}`` (HTTP 200) when nothing is
live, so the client can no-op cleanly.

The matching click route reuses the existing ``GET /sponsor/click`` handler
(it already attributes clicks + emits ``home.sponsor.click``), so a click from
the loading overlay is counted exactly like any other sponsor click.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.provider_name import register_template_filters, register_template_globals
from app.db.database import get_db
from app.db.models import AdSlot, Sponsor
from app.home import sponsor_store

router = APIRouter(prefix="/api", tags=["micro_ad"])

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))
# Shared registrars — every Jinja2Templates instance needs them (the /gas
# missing-canonical bug class; fragments rendered here may use the filters).
register_template_filters(_TEMPLATES)
register_template_globals(_TEMPLATES)

# Slots a caller may request. Mirrors the four-tier inventory; anything else
# falls back to the default so a typo can never 500 the loading overlay.
_ALLOWED_SLOTS: dict[str, AdSlot] = {s.value: s for s in AdSlot}
_DEFAULT_SLOT = AdSlot.MARQUEE


def _resolve_slot(raw: str | None) -> AdSlot:
    if raw is None:
        return _DEFAULT_SLOT
    return _ALLOWED_SLOTS.get(raw, _DEFAULT_SLOT)


def _pick_micro_ad(db: Session, slot: AdSlot) -> dict[str, Any] | None:
    """Highest-weight live sponsor in ``slot`` as a compact micro-ad dict, or None.

    Read-only: reuses ``sponsor_store.live_filter_for_slot`` but does NOT call
    the impression-bumping ``active_*`` helpers (see module docstring).
    """
    row = (
        sponsor_store.live_filter_for_slot(db.query(Sponsor), slot)
        .order_by(Sponsor.weight.desc(), Sponsor.created_at.desc())
        .first()
    )
    if row is None:
        return None
    return {
        "id": row.id,
        "slot": slot.value,
        "name": row.name,
        "headline": row.headline or row.name,
        "attribution_text": row.attribution_text or f"Sponsored by {row.name}",
        "cta_label": row.cta_label,
        # Click attribution goes through the existing /sponsor/click route so
        # the loading-overlay click is counted like any other sponsor click.
        "click_url": f"/sponsor/click?id={row.id}&slot={slot.value}",
        "image_url": row.image_url,
    }


@router.get("/micro_ad")
def get_micro_ad(
    request: Request,
    slot: str | None = None,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """JSON micro-ad payload for the loading overlay. ``{"micro_ad": null}`` when unsold."""
    del request  # signature parity with other routes; not needed here
    micro_ad = _pick_micro_ad(db, _resolve_slot(slot))
    return JSONResponse(content={"micro_ad": micro_ad})


@router.get("/micro_ad/partial", response_class=HTMLResponse, response_model=None)
def get_micro_ad_partial(
    request: Request,
    slot: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Server-rendered micro-ad partial (for non-JS / progressive-enhancement use)."""
    micro_ad = _pick_micro_ad(db, _resolve_slot(slot))
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="_partials/micro_ad.html",
        context={"micro_ad": micro_ad},
    )
