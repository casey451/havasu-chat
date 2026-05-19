"""View-model for the ``/provider/<slug>`` page.

Pure-ish ``build()`` (apart from a possible DB read for sponsor lookup —
deferred until Phase 2; V1 trusts ``Provider.tier`` + ``sponsored_until``)
that maps a ``Provider`` row + a ``viewer_is_owner`` flag into a flat,
template-friendly struct. The Jinja template should never branch on
business logic — only on the boolean flags below.

**Phase 1C — Pattern B:** reads prefer ``provider.entity`` extensions (hours,
location, contacts, taxonomy) when ``get_provider_by_slug`` eager-loads them;
legacy columns remain the fallback for rows without ENTITY linkage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.chat.disclosure_render import DISCLOSURE_WORD
from app.core.timezone import now_lake_havasu
from app.db.models import Provider
from app.home.queries import _format_phone
from app.providers import queries

# UX spec §5 method-to-copy table.
_VERIFICATION_METHOD_COPY: dict[str, str] = {
    "manual": "Verified by Hava",
    "owner_confirmed": "Confirmed by the owner",
    "scraper": "Auto-checked from public sources",
    "npi_registry": "Verified via NPI registry",
    "phone_call": "Confirmed by phone",
    "in_person": "Confirmed in person",
    "web_form_submission": "Confirmed via web form",
    "email_confirmation": "Confirmed by email",
    "none": "",
}


@dataclass(frozen=True)
class ProviderProfileVM:
    """Flat context object handed to ``provider_profile.html``.

    Frozen so the template can't accidentally mutate state. All
    business-logic decisions live in ``build()``; the template reads
    these fields verbatim.
    """

    provider_name: str
    category_label: str
    district: Optional[str]

    verified: bool
    last_verified_at: Optional[datetime]
    verification_method_copy: str
    freshness_band: str
    freshness_copy: str

    is_sponsored: bool
    is_featured: bool
    sponsor_disclosure_label: Optional[str]
    data_inconsistency_flag: bool

    google_rating: Optional[float]
    google_review_count: Optional[int]
    google_review_snippets: list[dict] = field(default_factory=list)

    call_phone: Optional[str] = None
    call_phone_display: Optional[str] = None
    directions_url: Optional[str] = None
    website_url: Optional[str] = None
    ask_hava_url: str = ""

    hero_photo_url: Optional[str] = None
    gallery_photo_urls: list[str] = field(default_factory=list)

    description: Optional[str] = None
    service_chips: list[str] = field(default_factory=list)
    service_area: list[str] = field(default_factory=list)
    service_area_only: bool = False
    address: Optional[str] = None

    hours_structured: Optional[dict] = None
    hours_freetext: Optional[str] = None
    is_open_now: Optional[bool] = None
    open_status_copy: Optional[str] = None

    show_claim_cta: bool = False
    show_upgrade_cta: bool = False
    viewer_is_owner: bool = False

    slug: str = ""

    district_chip_name: Optional[str] = None
    district_chip_url: Optional[str] = None
    seasonal_hours_active_season: Optional[str] = None
    seasonal_hours_active_rows: Optional[dict] = None
    season_status_copy: Optional[str] = None

    # Operational links rendered by the CTA region (placeholder routes in V1
    # — claim + upgrade flows haven't shipped yet).
    claim_url: str = ""
    upgrade_url: str = ""


@dataclass(frozen=True)
class HavaCardViewModel:
    """Flat card context for ``components/hava_card.html`` (Phase 6.1).

    Populated by :func:`app.providers.queries.build_card_view_model`; the
    template reads fields only — no inline ORM or business rules in Jinja.
    """

    entity_id: str
    entity_type: str
    name: str
    profile_url: str
    hero_photo_url: str | None
    category_slug: str
    category_label: str
    district_slug: str
    district_name: str
    status_line_text: str
    status_line_color: str
    freshness_band: str
    is_sponsored: bool
    boat_access_badge: bool
    heat_exposure_pill: str | None


def build(
    provider: Provider,
    *,
    db: Session,
    viewer_is_owner: bool = False,
    now: Optional[datetime] = None,
) -> ProviderProfileVM:
    """Map a ``Provider`` row into a ``ProviderProfileVM``.

    ``db`` is accepted for symmetry with future sponsor-lookup wiring;
    V1 reads only from the provider row itself.
    """
    now_dt = now or now_lake_havasu()

    band, freshness_copy = queries.derive_freshness(provider, now=now_dt)
    is_sponsored = _is_sponsored_now(provider, now=now_dt)
    is_featured = bool(provider.featured)
    data_inconsistency_flag = is_sponsored and not bool(provider.verified)

    verification_method_copy = _VERIFICATION_METHOD_COPY.get(
        provider.verification_method or "", ""
    )

    sponsor_disclosure_label = DISCLOSURE_WORD if is_sponsored else None

    call_display, call_digits = _format_phone(queries.derive_primary_phone_raw(provider))

    service_area_only = queries.derive_service_area_only(provider)
    service_area = queries.derive_service_area(provider)

    is_open, open_copy = queries.is_open_now(provider, now=now_dt)

    description = provider.featured_description or provider.description

    tier_is_free = (provider.tier or "free") == "free"
    show_claim_cta = tier_is_free and not bool(provider.verified)
    show_upgrade_cta = bool(provider.verified) and not is_sponsored

    slug = provider.slug or ""
    ent = getattr(provider, "entity", None)
    claim_slug = ""
    if ent is not None and getattr(ent, "slug", None):
        claim_slug = (ent.slug or "").strip()
    if not claim_slug:
        claim_slug = slug.strip()

    district_chip_name: Optional[str] = None
    district_chip_url: Optional[str] = None
    seasonal_hours_active_season: Optional[str] = None
    seasonal_hours_active_rows: Optional[dict] = None
    season_status_copy: Optional[str] = None
    hours_structured = queries.effective_hours_structured(provider)
    hours_freetext = provider.hours

    if ent is not None:
        dist = getattr(ent, "district", None)
        if dist is not None and getattr(dist, "slug", None):
            district_chip_name = str(dist.name or dist.slug)
            district_chip_url = f"/district/{dist.slug}"
        season_name, season_rows, season_copy = queries.effective_seasonal_hours(
            ent, now=now_dt
        )
        if season_rows is not None:
            seasonal_hours_active_season = season_name
            seasonal_hours_active_rows = season_rows
            season_status_copy = season_copy
            hours_structured = season_rows

    return ProviderProfileVM(
        provider_name=provider.provider_name,
        category_label=queries.category_label_for(provider),
        district=provider.district,
        verified=bool(provider.verified),
        last_verified_at=provider.last_verified_at,
        verification_method_copy=verification_method_copy,
        freshness_band=band,
        freshness_copy=freshness_copy,
        is_sponsored=is_sponsored,
        is_featured=is_featured,
        sponsor_disclosure_label=sponsor_disclosure_label,
        data_inconsistency_flag=data_inconsistency_flag,
        google_rating=provider.google_rating,
        google_review_count=provider.google_review_count,
        google_review_snippets=list(provider.google_review_snippets or []),
        call_phone=call_digits,
        call_phone_display=call_display,
        directions_url=queries.derive_directions_url(provider),
        website_url=queries.derive_website_url(provider),
        ask_hava_url=queries.derive_ask_hava_url(provider),
        hero_photo_url=queries.derive_hero_photo(provider),
        gallery_photo_urls=queries.derive_gallery(provider),
        description=description,
        service_chips=queries.derive_service_chips(provider),
        service_area=service_area,
        service_area_only=service_area_only,
        address=None if service_area_only else queries.derive_display_address(provider),
        hours_structured=hours_structured,
        hours_freetext=hours_freetext,
        district_chip_name=district_chip_name,
        district_chip_url=district_chip_url,
        seasonal_hours_active_season=seasonal_hours_active_season,
        seasonal_hours_active_rows=seasonal_hours_active_rows,
        season_status_copy=season_status_copy,
        is_open_now=is_open,
        open_status_copy=open_copy,
        show_claim_cta=show_claim_cta,
        show_upgrade_cta=show_upgrade_cta,
        viewer_is_owner=viewer_is_owner,
        slug=slug,
        claim_url=f"/claim/{claim_slug}" if claim_slug else "",
        upgrade_url=f"/upgrade/{slug}" if slug else "",
    )


def _is_sponsored_now(provider: Provider, *, now: datetime) -> bool:
    """``tier == "sponsored"`` AND ``sponsored_until`` is in the future
    (or unset, treated as open-ended)."""
    if (provider.tier or "") != "sponsored":
        return False
    until = provider.sponsored_until
    if until is None:
        return True
    if until.tzinfo is None and now.tzinfo is not None:
        # Compare naive vs naive — sponsored_until is a naive DateTime column.
        return until > now.replace(tzinfo=None)
    return until > now


__all__ = ["HavaCardViewModel", "ProviderProfileVM", "build"]
