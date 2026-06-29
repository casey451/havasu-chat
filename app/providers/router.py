"""Provider profile page route (directory pivot V1).

Renders ``/provider/{slug}`` via Jinja. Source of truth for copy/layout
is ``outputs/chatgpt_response_provider_profile_ux_spec.md``. All sponsor
labeling routes through ``app.chat.disclosure_render.DISCLOSURE_WORD``
so a single string change there propagates here.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.favorites import is_favorited
from app.chat.disclosure_render import DISCLOSURE_WORD
from app.core.provider_name import register_template_filters, register_template_globals
from app.core.rate_limit import limiter, public_html_rate_limit
from app.db.database import get_db
from app.db.models import Claim, Entity, Provider, User
from app.events.queries import venue_events_for_profile
from app.home import sandstone as home_sandstone
from app.providers import queries, view_models

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
register_template_filters(templates)
register_template_globals(templates)

router = APIRouter(tags=["providers"])


def _viewer_owns_provider(db: Session, *, current_user: User | None, provider: Provider) -> bool:
    if current_user is None:
        return False
    if getattr(current_user, "role", None) == "admin":
        return True
    claim = (
        db.query(Claim)
        .filter(
            Claim.user_id == current_user.id,
            Claim.entity_id == provider.entity_id,
            Claim.status == "verified",
        )
        .first()
    )
    return claim is not None


@router.get("/provider/{slug}", response_class=HTMLResponse, response_model=None)
@limiter.limit(public_html_rate_limit)
def serve_provider_profile(
    slug: str, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    provider = queries.get_provider_by_slug(db, slug)
    # P1.10: a provider merged away by the duplicate-slug op carries
    # attributes.merged_into_slug -> permanent redirect to the survivor so
    # old links/bookmarks/SERP entries keep working.
    if provider is not None and not provider.is_active:
        merged_into = (provider.attributes or {}).get("merged_into_slug")
        if merged_into and merged_into != slug:
            return RedirectResponse(url=f"/provider/{merged_into}", status_code=301)
    # 404 covers both missing rows and soft-hidden ones (is_active=False,
    # draft=True). End-users see the standard 404 surface; merchant
    # onboarding is a separate flow.
    if provider is None or not provider.is_active or provider.draft:
        raise HTTPException(status_code=404, detail="Provider not found")

    current_user = getattr(request.state, "current_user", None)
    viewer_is_owner = _viewer_owns_provider(db, current_user=current_user, provider=provider)
    vm = view_models.build(provider, db=db, viewer_is_owner=viewer_is_owner)
    entity = db.get(Entity, provider.entity_id)
    boat_access = entity.boat_access if entity is not None else None
    venue_events = venue_events_for_profile(db, provider, limit=5)
    nearby = queries.nearby_providers(db, provider, limit=3)
    # Track B1 resolution-path strips: a parent org's departments, the upward
    # link from a department child, and a multi-location business's other
    # locations. All empty/None unless the dedupe queue linked the rows.
    dept_children = queries.department_children(db, provider)
    parent_org = queries.parent_org_link(db, provider)
    other_locations = queries.sibling_locations(db, provider)
    already_saved = (
        bool(current_user)
        and bool(provider.entity_id)
        and is_favorited(db, current_user.id, provider.entity_id)
    )
    # THEME flag (Lake Ink & Brass, Phase 3b): the lake LocalBusiness profile
    # reskins the SAME ProviderProfileVM. Default stays desert until the flip.
    profile_template = "provider_profile_lake.html"
    return templates.TemplateResponse(
        request=request,
        name=profile_template,
        context={
            "vm": vm,
            "disclosure_word": DISCLOSURE_WORD,
            "current_user_id": current_user.id if current_user else "",
            "favorite_entity_id": provider.entity_id or "",
            "is_favorited": already_saved,
            "nearby_providers": nearby,
            "department_children": dept_children,
            "parent_org": parent_org,
            "other_locations": other_locations,
            "boat_access": boat_access,
            "has_boat_access": boat_access is not None,
            "venue_events": venue_events,
            "provider_name": vm.provider_name,
            # Sandstone header chrome (shared base): real nav + mega-menu.
            "primary_nav": home_sandstone.primary_nav(),
            "mega_columns": home_sandstone.mega_columns(db),
        },
    )
