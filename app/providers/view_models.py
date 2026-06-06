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
from datetime import datetime, time
from typing import Any, Optional

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
    category_url: str
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
    postal_address: Optional[dict] = None

    hours_structured: Optional[dict] = None
    hours_freetext: Optional[str] = None
    is_open_now: Optional[bool] = None
    open_status_copy: Optional[str] = None

    # Recurring classes/offerings attached to this venue's entity (the scraped
    # schedule-hunt findings land here as Schedule + Offering rows). Each item:
    # {title, days, time, cost, description}. Empty -> the section is omitted.
    class_schedule: list[dict] = field(default_factory=list)

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


_DAY_ORDER = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_DAY_ABBR = {
    "monday": "Mon", "tuesday": "Tue", "wednesday": "Wed", "thursday": "Thu",
    "friday": "Fri", "saturday": "Sat", "sunday": "Sun",
}


def _format_class_days(days: Any) -> str:
    """Canonical-ordered, abbreviated day list ("Mon, Wed, Fri")."""
    if not isinstance(days, (list, tuple)):
        return ""
    present = {d.strip().lower() for d in days if isinstance(d, str) and d.strip()}
    return ", ".join(_DAY_ABBR[d] for d in _DAY_ORDER if d in present)


def _format_class_time(start: time | None, end: time | None) -> str:
    """"6:00 AM – 7:00 AM" style range; one-sided or empty when times are missing."""
    def _hm(t: time | None) -> str | None:
        if not isinstance(t, time):
            return None
        hour = t.hour % 12 or 12
        ampm = "AM" if t.hour < 12 else "PM"
        return f"{hour}:{t.minute:02d} {ampm}"

    s, e = _hm(start), _hm(end)
    if s and e:
        return f"{s} – {e}"
    return s or e or ""


def build_class_schedule(entity: Any) -> list[dict]:
    """Pair an entity's recurring Schedule rows with their Offering (by class
    title) into display rows. Schedules carry day/time; offerings carry
    cost/description (schedule_publish writes Schedule.notes == Offering.name)."""
    if entity is None:
        return []
    offerings = list(getattr(entity, "offerings", None) or [])
    schedules = list(getattr(entity, "schedules", None) or [])
    off_by_title: dict[str, Any] = {}
    for o in offerings:
        key = (getattr(o, "name", "") or "").strip().lower()
        if key and key not in off_by_title:
            off_by_title[key] = o

    rows: list[dict] = []
    paired_offerings: set[str] = set()
    for s in schedules:
        title = (getattr(s, "notes", "") or "").strip()
        key = title.lower()
        o = off_by_title.get(key)
        if o is not None:
            paired_offerings.add(key)
        rows.append(
            {
                "title": title or (getattr(o, "name", None) if o else None) or "Class",
                "days": _format_class_days(getattr(s, "days_of_week", None)),
                "time": _format_class_time(getattr(s, "start_time", None), getattr(s, "end_time", None)),
                "cost": (getattr(o, "price_text", None) if o else None),
                "description": (getattr(o, "description", None) if o else None),
            }
        )

    # Offerings with no matching schedule (a named class/price but no fixed time).
    for o in offerings:
        key = (getattr(o, "name", "") or "").strip().lower()
        if not key or key in paired_offerings:
            continue
        rows.append(
            {
                "title": getattr(o, "name", None) or "Class",
                "days": "",
                "time": "",
                "cost": getattr(o, "price_text", None),
                "description": getattr(o, "description", None),
            }
        )
    return rows


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

    verification_method_copy = _VERIFICATION_METHOD_COPY.get(provider.verification_method or "", "")

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
        season_name, season_rows, season_copy = queries.effective_seasonal_hours(ent, now=now_dt)
        if season_rows is not None:
            seasonal_hours_active_season = season_name
            seasonal_hours_active_rows = season_rows
            season_status_copy = season_copy
            hours_structured = season_rows

    return ProviderProfileVM(
        provider_name=provider.provider_name,
        category_label=queries.category_label_for(provider),
        category_url=_category_url_for(provider),
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
        postal_address=None if service_area_only else queries.derive_postal_address(provider),
        hours_structured=hours_structured,
        hours_freetext=hours_freetext,
        district_chip_name=district_chip_name,
        district_chip_url=district_chip_url,
        seasonal_hours_active_season=seasonal_hours_active_season,
        seasonal_hours_active_rows=seasonal_hours_active_rows,
        season_status_copy=season_status_copy,
        is_open_now=is_open,
        open_status_copy=open_copy,
        class_schedule=build_class_schedule(ent),
        show_claim_cta=show_claim_cta,
        show_upgrade_cta=show_upgrade_cta,
        viewer_is_owner=viewer_is_owner,
        slug=slug,
        claim_url=f"/claim/{claim_slug}" if claim_slug else "",
        upgrade_url=f"/upgrade/{slug}" if slug else "",
    )


def _category_url_for(provider: Provider) -> str:
    """The actual category-page URL for the breadcrumb (P-1).

    The breadcrumb used to link to ``/categories`` (the Explore index) regardless
    of the business's category. Resolve the provider's legacy category to its most
    specific listing route — preferring a tile route (so a church links to
    Community, not the broad Services mega) — and fall back to Explore when unknown.
    Lazy import of ``CATEGORY_FILTERS`` avoids a categories↔providers import cycle.
    """
    from app.categories.queries import CATEGORY_FILTERS

    cat = (provider.category or "").strip().lower()
    if not cat:
        return "/categories"
    mega = {"services", "things-to-do", "eat-drink", "on-the-water"}
    tile_match: str | None = None
    mega_match: str | None = None
    for route, slugs in CATEGORY_FILTERS.items():
        if cat in slugs:
            if route in mega:
                mega_match = mega_match or route
            else:
                tile_match = tile_match or route
    route = tile_match or mega_match
    return f"/categories/{route}" if route else "/categories"


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
