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

from datetime import datetime, timedelta, timezone
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
    AdReservation,
    AdReservationStatus,
    AdSlot,
    Entity,
    Provider,
    Sponsor,
    SponsorStatus,
    UpgradeRequest,
    UpgradeRequestStatus,
    User,
)
from app.db.monetization_models import Placement, PlacementStatus

# Allowed forward transitions for an ad reservation's status FSM.
_AD_RESERVATION_NEXT: dict[str, frozenset[str]] = {
    AdReservationStatus.PENDING.value: frozenset(
        {AdReservationStatus.CONTACTED.value, AdReservationStatus.DECLINED.value}
    ),
    AdReservationStatus.CONTACTED.value: frozenset(
        {AdReservationStatus.CLOSED.value, AdReservationStatus.DECLINED.value}
    ),
}

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

    # ── admin ad-reservation queue (manual-invoice "Reserve this spot") ───────

    @router.get("/ad-reservations", response_class=HTMLResponse, response_model=None)
    def admin_ad_reservations(
        request: Request, db: Session = Depends(get_db)
    ) -> HTMLResponse | RedirectResponse:
        """Queue of /portal/advertise reservations. Pending first, then the rest.

        No billing/payment here — these are leads Casey closes by invoice. The
        status FSM advances pending → contacted → closed (or → declined).
        """
        redir = _admin_guard(request)
        if redir is not None:
            return redir
        rows = (
            db.execute(
                select(AdReservation).order_by(
                    AdReservation.status.asc(), AdReservation.created_at.desc()
                )
            )
            .scalars()
            .all()
        )
        pending = [r for r in rows if r.status == AdReservationStatus.PENDING.value]
        others = [r for r in rows if r.status != AdReservationStatus.PENDING.value]

        def _row(r: AdReservation) -> dict[str, object]:
            return {
                "id": r.id,
                "product_name": r.product_name,
                "product_key": r.product_key,
                "business_name": r.business_name,
                "contact_name": r.contact_name,
                "contact_email": r.contact_email,
                "contact_phone": r.contact_phone,
                "category_or_notes": r.category_or_notes,
                "status": r.status,
                "created_at": r.created_at,
                "next": sorted(_AD_RESERVATION_NEXT.get(r.status, frozenset())),
            }

        return _TEMPLATES.TemplateResponse(
            request=request,
            name="admin_ad_reservations.html",
            context={
                "pending": [_row(r) for r in pending],
                "others": [_row(r) for r in others],
            },
        )

    @router.post("/ad-reservations/{reservation_id}/status", response_model=None)
    def admin_ad_reservation_set_status(
        request: Request,
        reservation_id: str,
        status: str = Form(...),
        db: Session = Depends(get_db),
    ) -> RedirectResponse:
        """Advance a reservation's status along the allowed FSM transitions."""
        redir = _admin_guard(request)
        if redir is not None:
            return redir
        res = db.get(AdReservation, reservation_id)
        if res is None:
            raise HTTPException(status_code=404, detail="ad_reservation_not_found")
        allowed = _AD_RESERVATION_NEXT.get(res.status, frozenset())
        if status not in allowed:
            raise HTTPException(status_code=400, detail="invalid_status_transition")
        res.status = status
        db.add(res)
        db.commit()
        return RedirectResponse(url="/admin/ad-reservations", status_code=303)

    # ── admin placement queue (Phase F §8 — activate self-serve purchases) ────

    @router.get("/placements", response_class=HTMLResponse, response_model=None)
    def admin_placements(
        request: Request, db: Session = Depends(get_db)
    ) -> HTMLResponse | RedirectResponse:
        """Queue of monetization Placements. Pending (awaiting activation) first.

        Activating a placement is what makes it serve — until then it's inert.
        No payment is processed here; the operator confirms the price and term
        (Stripe checkout is a later increment)."""
        redir = _admin_guard(request)
        if redir is not None:
            return redir
        rows = (
            db.execute(
                select(Placement).order_by(
                    Placement.status.asc(), Placement.created_at.desc()
                )
            )
            .scalars()
            .all()
        )
        prov_ids = {r.provider_id for r in rows}
        prov_by_id = (
            {
                p.id: p
                for p in db.execute(
                    select(Provider).where(Provider.id.in_(prov_ids))
                )
                .scalars()
                .all()
            }
            if prov_ids
            else {}
        )

        def _row(r: Placement) -> dict[str, object]:
            prov = prov_by_id.get(r.provider_id)
            return {
                "id": r.id,
                "provider_name": prov.provider_name if prov else r.provider_id,
                "provider_slug": prov.slug if prov else None,
                "placement_type": r.placement_type,
                "category_slug": r.category_slug,
                "rank_tier": r.rank_tier,
                "billing_type": r.billing_type,
                "price_dollars": f"{r.price_cents / 100:.0f}" if r.price_cents else "",
                "status": r.status,
                "created_at": r.created_at,
                "paid_through": r.paid_through,
            }

        pending = [_row(r) for r in rows if r.status == PlacementStatus.pending.value]
        others = [_row(r) for r in rows if r.status != PlacementStatus.pending.value]
        return _TEMPLATES.TemplateResponse(
            request=request,
            name="admin_placements.html",
            context={"pending": pending, "others": others},
        )

    @router.post("/placements/{placement_id}/activate", response_model=None)
    def admin_placement_activate(
        request: Request,
        placement_id: str,
        price_cents: str = Form(default=""),
        term_days: str = Form(default="30"),
        db: Session = Depends(get_db),
    ) -> RedirectResponse:
        """Flip a pending placement to active: it starts serving immediately and
        renders the Sponsored label. Optionally override the priced figure and set
        the paid-through term."""
        redir = _admin_guard(request)
        if redir is not None:
            return redir
        p = db.get(Placement, placement_id)
        if p is None:
            raise HTTPException(status_code=404, detail="placement_not_found")
        if p.status != PlacementStatus.pending.value:
            raise HTTPException(status_code=400, detail="not_pending")
        now = _naive_utc_now()
        days = int(term_days) if term_days.strip().isdigit() else 30
        p.status = PlacementStatus.active.value
        p.starts_at = now
        p.paid_through = now + timedelta(days=days)
        if price_cents.strip().isdigit():
            p.price_cents = int(price_cents)
        db.add(p)
        db.commit()
        return RedirectResponse(url="/admin/placements", status_code=303)

    @router.post("/placements/{placement_id}/release", response_model=None)
    def admin_placement_release(
        request: Request, placement_id: str, db: Session = Depends(get_db)
    ) -> RedirectResponse:
        """Release a placement (free the spot). Stops serving immediately."""
        redir = _admin_guard(request)
        if redir is not None:
            return redir
        p = db.get(Placement, placement_id)
        if p is None:
            raise HTTPException(status_code=404, detail="placement_not_found")
        p.status = PlacementStatus.released.value
        db.add(p)
        db.commit()
        return RedirectResponse(url="/admin/placements", status_code=303)


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
