"""Business portal routes (Phase 2 §5b).

Public front door for business owners: the claim entry point plus the self-serve
placement purchase + ad-creative flow (Phase F). Payments are intentionally NOT
wired yet — placements land ``pending`` for operator activation; Stripe checkout
is a later increment once the owner picks a processor + configures keys.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.provider_name import register_template_filters, register_template_globals
from app.db.database import get_db
from app.db.monetization_models import PlacementStatus
from app.home.queries import CATEGORY_LABELS
from app.monetization import serving
from app.portal import creative_store
from app.portal import placements as placement_logic

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)

router = APIRouter(prefix="/portal", tags=["portal"])


def _t(request: Request, name: str) -> str:
    """Serve the Lake Ink & Brass variant when the THEME flag resolves to lake
    (Phase 4c). ``foo.html`` -> ``foo_lake.html``; default stays desert until the
    Phase-8 flip — see app/core/theme.py."""
    if getattr(request.state, "theme", "desert") == "lake":
        return f"{name[:-5]}_lake.html"
    return name


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def portal_home(request: Request) -> HTMLResponse:
    """Portal landing — claim or advertise."""
    return templates.TemplateResponse(
        request=request, name=_t(request, "portal_index.html"), context={}
    )


@router.get("/claim", response_class=HTMLResponse)
def portal_claim(request: Request) -> HTMLResponse:
    """Claim entry point: find your listing (then claim it from its page) or add
    a new one. The per-listing claim itself lives at /claim/{slug} via the
    provider profile's 'Claim this listing' CTA."""
    return templates.TemplateResponse(
        request=request, name=_t(request, "portal_claim.html"), context={}
    )


# ── shared helpers ────────────────────────────────────────────────────────────


def _category_options(db: Session) -> list[tuple[str, str]]:
    """(slug, label) pairs for the category-sponsorship dropdown.

    Sources the CANONICAL taxonomy departments (``Category`` level-0 rows —
    the same pages the nav and /categories index render), not the legacy
    map-scope ``CATEGORY_LABELS`` list the form used to offer: that list had
    13 scopes that don't match the sellable department pages (no Beauty,
    Fitness & Wellness, Family & Education, Things to Do…) and included
    "Events", which is sold separately as Event Boost (audit §13.1 — a paying
    advertiser couldn't pick the page the product actually pins them to).
    Falls back to the legacy list on any DB hiccup so the revenue form never
    renders an empty dropdown. Order matches the nav (taxonomy sort_order).
    """
    from app.categories.leaf_pages import all_departments  # lazy: avoid import cycle

    try:
        rows = all_departments(db)
    except Exception:  # noqa: BLE001 — fall back, never blank the form
        rows = []
    if rows:
        return [(dept.slug, dept.name) for dept, _leaf_count, _total in rows]
    return sorted(CATEGORY_LABELS.items(), key=lambda kv: kv[1])


# ── self-serve placement purchase (Phase F §8; merchant-gated, NO payment yet) ─


def _indicative_prices(db: Session) -> dict:
    """Global-default prices (cents) for the buy form's rate display."""
    return {
        "homepage_rotating": serving.price_for(db, "homepage_rotating"),
        "page_ad": serving.price_for(db, "page_ad"),
        "category_rank": {
            t: serving.price_for(db, "category_rank", rank_tier=t) for t in range(1, 6)
        },
    }


@router.get("/placements", response_class=HTMLResponse, response_model=None)
def portal_placements(
    request: Request, db: Session = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    """A merchant's placement dashboard: their claimed listings + any placements
    held (pending or active). Login-gated; an unclaimed visitor is sent to claim."""
    user = get_current_user(request)
    if user is None:
        return RedirectResponse(url="/login?next=/portal/placements", status_code=303)
    providers = placement_logic.claimed_providers(db, user.id)
    placements = placement_logic.active_placements_for_providers(
        db, [p.id for p in providers]
    )
    from app.billing import config as billing_config
    from app.billing import service as billing_service

    billing_on = billing_config.billing_enabled()
    has_billing_account = bool(
        billing_on and billing_service.customer_id_for_user_placements(placements)
    )
    return templates.TemplateResponse(
        request=request,
        name=_t(request, "portal_placements.html"),
        context={
            "providers": providers,
            "placements": placements,
            "prov_by_id": {p.id: p for p in providers},
            "type_labels": {
                k: v["label"] for k, v in placement_logic.PURCHASABLE_TYPES.items()
            },
            "purchased": request.query_params.get("purchased") == "1",
            # When billing is live a pending placement shows a "Pay now" button
            # (→ Stripe Checkout) and a "Manage billing" link (→ Customer Portal).
            # Both are hidden while dormant, so today's operator-confirm flow is
            # unchanged.
            "billing_enabled": billing_on,
            "has_billing_account": has_billing_account,
            "PENDING": PlacementStatus.pending.value,
            "ACTIVE": PlacementStatus.active.value,
        },
    )


@router.get("/placements/new", response_class=HTMLResponse, response_model=None)
def portal_placement_new_get(
    request: Request, provider_id: str = "", db: Session = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    """Render the buy-a-placement form for the merchant's claimed listings."""
    user = get_current_user(request)
    if user is None:
        return RedirectResponse(url="/login?next=/portal/placements/new", status_code=303)
    providers = placement_logic.claimed_providers(db, user.id)
    if not providers:
        return RedirectResponse(url="/portal/claim", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name=_t(request, "portal_placement_new.html"),
        context={
            "providers": providers,
            "selected_provider_id": provider_id,
            "categories": _category_options(db),
            "types": placement_logic.PURCHASABLE_TYPES,
            "prices": _indicative_prices(db),
            "creatives": _merchant_creatives(db, providers),
            "errors": {},
            "form": {},
        },
    )


@router.post("/placements/new", response_class=HTMLResponse, response_model=None)
def portal_placement_new_post(
    request: Request,
    provider_id: str = Form(...),
    placement_type: str = Form(...),
    category_slug: str = Form(default=""),
    rank_tier: str = Form(default=""),
    billing_type: str = Form(default="monthly"),
    creative_id: str = Form(default=""),
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    """Create a ``pending`` placement after checking ownership + inputs.

    No payment is taken — the placement awaits operator confirmation (and, later,
    Stripe checkout). A pending placement is not served, so this is side-effect
    free on the live site until activated.
    """
    user = get_current_user(request)
    if user is None:
        return RedirectResponse(url="/login?next=/portal/placements/new", status_code=303)
    if not placement_logic.owns_provider(db, user.id, provider_id):
        raise HTTPException(status_code=403, detail="not_your_listing")

    cat = category_slug.strip() or None
    tier_int = int(rank_tier) if rank_tier.strip().isdigit() else None
    errors = placement_logic.validate_purchase(
        placement_type, category_slug=cat, rank_tier=tier_int, billing_type=billing_type
    )
    # A category, when required, must be a real department option (not hand-typed).
    if cat is not None and "category_slug" not in errors:
        if cat not in dict(_category_options(db)):
            errors["category_slug"] = "Pick a category from the list."

    if errors:
        providers = placement_logic.claimed_providers(db, user.id)
        return templates.TemplateResponse(
            request=request,
            name=_t(request, "portal_placement_new.html"),
            context={
                "providers": providers,
                "selected_provider_id": provider_id,
                "categories": _category_options(db),
                "types": placement_logic.PURCHASABLE_TYPES,
                "prices": _indicative_prices(db),
                "creatives": _merchant_creatives(db, providers),
                "errors": errors,
                "form": {
                    "provider_id": provider_id,
                    "placement_type": placement_type,
                    "category_slug": category_slug,
                    "rank_tier": rank_tier,
                    "billing_type": billing_type,
                    "creative_id": creative_id,
                },
            },
            status_code=400,
        )

    placement = placement_logic.create_pending_placement(
        db,
        provider_id=provider_id,
        placement_type=placement_type,
        category_slug=cat,
        rank_tier=tier_int,
        billing_type=billing_type,
        creative_id=(creative_id.strip() or None),
    )

    # Self-serve purchase: when billing is live, take the merchant straight to
    # Stripe Checkout for the placement they just configured (no lead-capture
    # detour). While billing is dormant this is skipped and the placement waits
    # for operator confirmation — the pre-billing flow, unchanged.
    from app.billing import config as billing_config
    from app.billing import service as billing_service

    if billing_config.billing_enabled():
        base = str(request.base_url).rstrip("/")
        url = billing_service.create_checkout_session(
            db,
            placement,
            success_url=f"{base}/portal/placements?purchased=1",
            cancel_url=f"{base}/portal/placements",
            customer_email=getattr(user, "email", None),
        )
        if url:
            return RedirectResponse(url=url, status_code=303)

    return RedirectResponse(url="/portal/placements?purchased=1", status_code=303)


# ── ad creatives (URL-based; F2) ──────────────────────────────────────────────


def _merchant_creatives(db: Session, providers: list) -> list[dict]:
    """Flattened (creative, provider-name) list across a merchant's listings."""
    out: list[dict] = []
    for prov in providers:
        for c in placement_logic.creatives_for_provider(db, prov.id):
            out.append(
                {
                    "id": c.id,
                    "provider_id": prov.id,
                    "provider_name": prov.provider_name,
                    "headline": c.headline,
                    "image_url": c.image_url,
                }
            )
    return out


@router.get("/creatives", response_class=HTMLResponse, response_model=None)
def portal_creatives(
    request: Request, db: Session = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    """List the merchant's ad creatives and a form to add one (URL-based)."""
    user = get_current_user(request)
    if user is None:
        return RedirectResponse(url="/login?next=/portal/creatives", status_code=303)
    providers = placement_logic.claimed_providers(db, user.id)
    if not providers:
        return RedirectResponse(url="/portal/claim", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name=_t(request, "portal_creatives.html"),
        context={
            "providers": providers,
            "creatives": _merchant_creatives(db, providers),
            "errors": {},
            "form": {},
        },
    )


@router.post("/creatives", response_class=HTMLResponse, response_model=None)
async def portal_creatives_create(
    request: Request,
    provider_id: str = Form(...),
    headline: str = Form(default=""),
    body: str = Form(default=""),
    cta_label: str = Form(default=""),
    cta_url: str = Form(default=""),
    image_url: str = Form(default=""),
    image_url_mobile: str = Form(default=""),
    image_file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    """Create a creative for a listing the merchant owns.

    The image can be EITHER a hosted URL (``image_url``) or an uploaded file
    (``image_file``); an upload wins and populates ``image_url`` with the stored
    ``/media/creatives/…`` path. Uploads are validated as real images and saved
    to the Railway volume (see :mod:`app.portal.creative_store`).
    """
    user = get_current_user(request)
    if user is None:
        return RedirectResponse(url="/login?next=/portal/creatives", status_code=303)
    if not placement_logic.owns_provider(db, user.id, provider_id):
        raise HTTPException(status_code=403, detail="not_your_listing")

    errors: dict[str, str] = {}

    # Optional binary upload — takes precedence over a typed image URL.
    if image_file is not None and (image_file.filename or "").strip():
        content = await image_file.read(creative_store.MAX_IMAGE_BYTES + 1)
        if len(content) > creative_store.MAX_IMAGE_BYTES:
            errors["image_url"] = "Image is larger than the 5 MB limit."
        else:
            try:
                image_url = creative_store.save_creative_image(
                    content, declared_mime=image_file.content_type
                )
            except creative_store.CreativeImageError:
                errors["image_url"] = "That file isn't a supported image (JPG, PNG, WebP, GIF)."

    if not headline.strip() and not image_url.strip() and "image_url" not in errors:
        errors["headline"] = "Give the creative a headline or an image."

    if errors:
        providers = placement_logic.claimed_providers(db, user.id)
        return templates.TemplateResponse(
            request=request,
            name=_t(request, "portal_creatives.html"),
            context={
                "providers": providers,
                "creatives": _merchant_creatives(db, providers),
                "errors": errors,
                "form": {
                    "provider_id": provider_id,
                    "headline": headline,
                    "body": body,
                    "cta_label": cta_label,
                    "cta_url": cta_url,
                    "image_url": image_url,
                    "image_url_mobile": image_url_mobile,
                },
            },
            status_code=400,
        )

    placement_logic.create_creative(
        db,
        provider_id=provider_id,
        headline=headline.strip(),
        body=body.strip(),
        cta_label=cta_label.strip(),
        cta_url=cta_url.strip(),
        image_url=image_url.strip(),
        image_url_mobile=image_url_mobile.strip(),
    )
    return RedirectResponse(url="/portal/creatives", status_code=303)
