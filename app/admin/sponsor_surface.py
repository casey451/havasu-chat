"""Phase A4 — ad-surface activation against the existing Sponsor schema.

Three pieces, all built on the EXISTING ``Sponsor`` model (no fork):

1. Admin slot-inventory view (``GET /admin/sponsors``) + status-FSM action
   forms (approve / pause / activate-toggle), plus a per-slot sold-vs-available
   summary. Mirrors the ``/admin/claims`` pattern. NO pricing anywhere.

2. (micro-ad lives in ``app/api/routes/micro_ad.py`` — not here.)

3. Claim-your-listing upgrade funnel:
     * merchant ``GET/POST /merchant/upgrade/{slug}`` — a verified owner of an
       entity requests a featured/spotlight upgrade. Capture only; NO billing.
     * admin ``GET /admin/upgrade-requests`` queue + ``/approve`` (optionally
       spinning out a live ``Sponsor`` row) + ``/decline``.

Pricing, what-is-sold, inventory caps, and free-vs-paid are deliberately NOT
implemented here — those are Casey product decisions (see PR FLAGs).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.auth import COOKIE_NAME, verify_admin_cookie
from app.auth.claims import entity_is_claimable, find_existing_claim, get_entity_by_slug
from app.auth.dependencies import get_current_user
from app.core.provider_name import register_template_filters, register_template_globals
from app.db.database import get_db
from app.db.models import (
    AdSlot,
    Entity,
    Sponsor,
    SponsorStatus,
    UpgradeRequest,
    UpgradeRequestStatus,
    User,
)

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
register_template_filters(_TEMPLATES)
register_template_globals(_TEMPLATES)

# Slots a merchant may request. All four tiers are valid request targets.
_REQUESTABLE_SLOTS: frozenset[str] = frozenset(s.value for s in AdSlot)


def _admin_guard(request: Request) -> RedirectResponse | None:
    """Mirror of admin.router._guard (cookie OR admin-role user)."""
    if verify_admin_cookie(request.cookies.get(COOKIE_NAME)):
        return None
    current_user = getattr(request.state, "current_user", None)
    if current_user is not None and getattr(current_user, "role", None) == "admin":
        return None
    if current_user is not None:
        raise HTTPException(status_code=403, detail="admin_only")
    return RedirectResponse(url="/admin/login", status_code=302)


def _naive_utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ctr(impressions: int, clicks: int) -> float:
    return round((clicks / impressions) * 100, 2) if impressions else 0.0


# ── admin slot-inventory view ────────────────────────────────────────────────


def register_sponsor_admin_routes(router: APIRouter) -> None:
    """Attach the sponsor-inventory + upgrade-review routes to the admin router."""

    @router.get("/sponsors", response_class=HTMLResponse, response_model=None)
    def admin_sponsors_inventory(
        request: Request, db: Session = Depends(get_db)
    ) -> HTMLResponse | RedirectResponse:
        redir = _admin_guard(request)
        if redir is not None:
            return redir
        rows = (
            db.execute(select(Sponsor).order_by(Sponsor.slot.asc(), Sponsor.weight.desc()))
            .scalars()
            .all()
        )
        now = _naive_utc_now()
        groups: dict[str, dict[str, object]] = {}
        for slot in AdSlot:
            groups[slot.value] = {"slot": slot.value, "sponsors": [], "sold": 0}
        for sp in rows:
            # "Sold" = currently live (approved + active + within window). This is
            # a read-only count; capacity per slot is a Casey decision (FLAG), so
            # "available" is shown as a dash rather than a fabricated cap.
            is_live = (
                sp.status == SponsorStatus.APPROVED.value
                and sp.active
                and (sp.starts_at is None or sp.starts_at <= now)
                and (sp.ends_at is None or sp.ends_at > now)
            )
            entry = groups.get(sp.slot)
            if entry is None:
                groups[sp.slot] = {"slot": sp.slot, "sponsors": [], "sold": 0}
                entry = groups[sp.slot]
            if is_live:
                entry["sold"] = int(entry["sold"]) + 1  # type: ignore[arg-type]
            entry["sponsors"].append(  # type: ignore[union-attr]
                {
                    "id": sp.id,
                    "name": sp.name,
                    "status": sp.status,
                    "active": sp.active,
                    "weight": sp.weight,
                    "starts_at": sp.starts_at,
                    "ends_at": sp.ends_at,
                    "impressions": sp.impressions,
                    "clicks": sp.clicks,
                    "ctr": _ctr(sp.impressions, sp.clicks),
                    "is_live": is_live,
                }
            )
        return _TEMPLATES.TemplateResponse(
            request=request,
            name="admin_sponsors_inventory.html",
            context={"groups": [groups[s.value] for s in AdSlot]},
        )

    @router.post("/sponsors/{sponsor_id}/approve", response_model=None)
    def admin_sponsor_approve(
        request: Request, sponsor_id: str, db: Session = Depends(get_db)
    ) -> RedirectResponse:
        redir = _admin_guard(request)
        if redir is not None:
            return redir
        sp = db.get(Sponsor, sponsor_id)
        if sp is None:
            raise HTTPException(status_code=404, detail="sponsor_not_found")
        sp.status = SponsorStatus.APPROVED.value
        sp.approved_at = _naive_utc_now()
        cu = getattr(request.state, "current_user", None)
        if cu is not None and getattr(cu, "role", None) == "admin":
            sp.approved_by = cu.id
        sp.paused_at = None
        sp.paused_reason = None
        db.add(sp)
        db.commit()
        return RedirectResponse(url="/admin/sponsors", status_code=303)

    @router.post("/sponsors/{sponsor_id}/pause", response_model=None)
    def admin_sponsor_pause(
        request: Request,
        sponsor_id: str,
        reason: str = Form(default=""),
        db: Session = Depends(get_db),
    ) -> RedirectResponse:
        redir = _admin_guard(request)
        if redir is not None:
            return redir
        sp = db.get(Sponsor, sponsor_id)
        if sp is None:
            raise HTTPException(status_code=404, detail="sponsor_not_found")
        sp.status = SponsorStatus.PAUSED.value
        sp.paused_at = _naive_utc_now()
        sp.paused_reason = reason.strip() or None
        db.add(sp)
        db.commit()
        return RedirectResponse(url="/admin/sponsors", status_code=303)

    @router.post("/sponsors/{sponsor_id}/toggle-active", response_model=None)
    def admin_sponsor_toggle_active(
        request: Request, sponsor_id: str, db: Session = Depends(get_db)
    ) -> RedirectResponse:
        """Flip the kill-switch ``active`` boolean (emergency on/off, bypasses FSM)."""
        redir = _admin_guard(request)
        if redir is not None:
            return redir
        sp = db.get(Sponsor, sponsor_id)
        if sp is None:
            raise HTTPException(status_code=404, detail="sponsor_not_found")
        sp.active = not sp.active
        db.add(sp)
        db.commit()
        return RedirectResponse(url="/admin/sponsors", status_code=303)

    # ── admin upgrade-request review queue ───────────────────────────────────

    @router.get("/upgrade-requests", response_class=HTMLResponse, response_model=None)
    def admin_upgrade_requests(
        request: Request, db: Session = Depends(get_db)
    ) -> HTMLResponse | RedirectResponse:
        redir = _admin_guard(request)
        if redir is not None:
            return redir
        stmt = (
            select(UpgradeRequest, User, Entity)
            .join(User, UpgradeRequest.user_id == User.id)
            .join(Entity, UpgradeRequest.entity_id == Entity.id)
            .where(UpgradeRequest.status == UpgradeRequestStatus.PENDING.value)
            .order_by(UpgradeRequest.created_at.asc())
        )
        items: list[dict[str, object]] = []
        for req, user, ent in db.execute(stmt).all():
            items.append(
                {
                    "id": req.id,
                    "email": user.email,
                    "entity_name": ent.name or ent.slug or req.entity_id,
                    "requested_slot": req.requested_slot,
                    "message": req.message,
                    "created_at": req.created_at,
                }
            )
        return _TEMPLATES.TemplateResponse(
            request=request,
            name="admin_upgrade_requests.html",
            context={"requests": items, "slots": [s.value for s in AdSlot]},
        )

    @router.post("/upgrade-requests/{request_id}/approve", response_model=None)
    def admin_upgrade_approve(
        request: Request,
        request_id: str,
        create_sponsor: str = Form(default=""),
        admin_note: str = Form(default=""),
        db: Session = Depends(get_db),
    ) -> RedirectResponse:
        redir = _admin_guard(request)
        if redir is not None:
            return redir
        req = db.get(UpgradeRequest, request_id)
        if req is None or req.status != UpgradeRequestStatus.PENDING.value:
            raise HTTPException(status_code=404, detail="upgrade_request_not_found")
        req.status = UpgradeRequestStatus.APPROVED.value
        req.reviewed_at = _naive_utc_now()
        req.admin_note = admin_note.strip() or None
        cu = getattr(request.state, "current_user", None)
        if cu is not None and getattr(cu, "role", None) == "admin":
            req.reviewed_by = cu.id
        # Optionally spin out a DRAFT Sponsor row from the request. It is created
        # in DRAFT (NOT live) so an admin still sets copy/window/pricing-tier and
        # explicitly approves it via /admin/sponsors. NO billing here.
        if create_sponsor:
            ent = db.get(Entity, req.entity_id)
            sponsor = Sponsor(
                name=(ent.name if ent and ent.name else "Pending advertiser"),
                slot=req.requested_slot,
                status=SponsorStatus.DRAFT.value,
                cta_url=(f"/provider/{ent.slug}" if ent and ent.slug else "/"),
                business_id=req.business_id,
                active=False,
            )
            db.add(sponsor)
            db.flush()
            req.created_sponsor_id = sponsor.id
        db.add(req)
        db.commit()
        return RedirectResponse(url="/admin/upgrade-requests", status_code=303)

    @router.post("/upgrade-requests/{request_id}/decline", response_model=None)
    def admin_upgrade_decline(
        request: Request,
        request_id: str,
        admin_note: str = Form(default=""),
        db: Session = Depends(get_db),
    ) -> RedirectResponse:
        redir = _admin_guard(request)
        if redir is not None:
            return redir
        req = db.get(UpgradeRequest, request_id)
        if req is None or req.status != UpgradeRequestStatus.PENDING.value:
            raise HTTPException(status_code=404, detail="upgrade_request_not_found")
        req.status = UpgradeRequestStatus.DECLINED.value
        req.reviewed_at = _naive_utc_now()
        req.admin_note = admin_note.strip() or None
        cu = getattr(request.state, "current_user", None)
        if cu is not None and getattr(cu, "role", None) == "admin":
            req.reviewed_by = cu.id
        db.add(req)
        db.commit()
        return RedirectResponse(url="/admin/upgrade-requests", status_code=303)


# ── merchant-facing upgrade request capture ──────────────────────────────────

merchant_upgrade_router = APIRouter(prefix="/merchant", tags=["merchant-upgrade"])


def _owns_entity(db: Session, user_id: str, entity_id: str) -> bool:
    """True when the user has a VERIFIED claim on the entity."""
    claim = find_existing_claim(db, user_id, entity_id)
    return claim is not None and claim.status == "verified"


@merchant_upgrade_router.get("/upgrade/{slug}", response_class=HTMLResponse, response_model=None)
def merchant_upgrade_get(
    slug: str, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    """Show the upgrade-request form for a listing the current user owns."""
    user = get_current_user(request)
    if user is None:
        from urllib.parse import quote

        return RedirectResponse(
            url=f"/login?next={quote(f'/merchant/upgrade/{slug}', safe='')}",
            status_code=303,
        )
    ent = get_entity_by_slug(db, slug)
    if ent is None:
        raise HTTPException(status_code=404, detail="entity_not_found")
    if not entity_is_claimable(ent.entity_type):
        raise HTTPException(status_code=400, detail="not_claimable")
    if not _owns_entity(db, user.id, ent.id):
        raise HTTPException(status_code=403, detail="not_owner")
    existing = (
        db.query(UpgradeRequest)
        .filter(
            UpgradeRequest.user_id == user.id,
            UpgradeRequest.entity_id == ent.id,
            UpgradeRequest.status == UpgradeRequestStatus.PENDING.value,
        )
        .first()
    )
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="merchant_upgrade_form.html",
        context={
            "entity": ent,
            "slots": [s.value for s in AdSlot],
            "pending": existing is not None,
        },
    )


@merchant_upgrade_router.post("/upgrade/{slug}", response_class=HTMLResponse, response_model=None)
def merchant_upgrade_post(
    slug: str,
    request: Request,
    requested_slot: str = Form(...),
    message: str = Form(default=""),
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    user = get_current_user(request)
    if user is None:
        from urllib.parse import quote

        return RedirectResponse(
            url=f"/login?next={quote(f'/merchant/upgrade/{slug}', safe='')}",
            status_code=303,
        )
    ent = get_entity_by_slug(db, slug)
    if ent is None:
        raise HTTPException(status_code=404, detail="entity_not_found")
    if not entity_is_claimable(ent.entity_type):
        raise HTTPException(status_code=400, detail="not_claimable")
    if not _owns_entity(db, user.id, ent.id):
        raise HTTPException(status_code=403, detail="not_owner")
    if requested_slot not in _REQUESTABLE_SLOTS:
        raise HTTPException(status_code=400, detail="invalid_slot")
    # Idempotent: don't stack duplicate pending requests for the same listing.
    existing = (
        db.query(UpgradeRequest)
        .filter(
            UpgradeRequest.user_id == user.id,
            UpgradeRequest.entity_id == ent.id,
            UpgradeRequest.status == UpgradeRequestStatus.PENDING.value,
        )
        .first()
    )
    if existing is None:
        db.add(
            UpgradeRequest(
                user_id=user.id,
                entity_id=ent.id,
                business_id=getattr(ent, "provider_id", None),
                requested_slot=requested_slot,
                message=message.strip() or None,
                status=UpgradeRequestStatus.PENDING.value,
            )
        )
        db.commit()
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="merchant_upgrade_form.html",
        context={"entity": ent, "slots": [s.value for s in AdSlot], "pending": True},
    )
