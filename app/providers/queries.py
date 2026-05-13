"""Provider profile DB queries + derivations.

Pure-ish helpers consumed by ``app.providers.view_models.build``. Each
derive_* function takes a ``Provider`` and returns primitives so the
view-model layer can stay flat. Time-dependent helpers accept an
optional ``now`` argument for testability (matches the
``now_lake_havasu()`` injection pattern used elsewhere in the app).

**Phase 1C — Pattern B (Legacy + alias):** callers continue to fetch ``Provider``
rows; enriched reads resolve through ``provider.entity`` → locations / hours /
contact_points / ``entity_categories`` when ``entity_id`` is populated
(migrated ENTITY schema). Legacy columns remain for orphan rows and Phase 1D
dual-write transition.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Optional
from urllib.parse import quote

from sqlalchemy.orm import Session, joinedload

from app.core.timezone import LAKE_HAVASU_TZ, now_lake_havasu
from app.db.models import Entity, EntityCategory, Hours, Provider
from app.home.queries import CATEGORY_LABELS, LEGACY_PROVIDER_CATEGORY_LABELS


def get_provider_by_slug(db: Session, slug: str) -> Optional[Provider]:
    """Return the active Provider with this slug, or None."""
    return (
        db.query(Provider)
        .options(
            joinedload(Provider.category_ref),
            joinedload(Provider.entity).joinedload(Entity.location),
            joinedload(Provider.entity).selectinload(Entity.hours),
            joinedload(Provider.entity).selectinload(Entity.contact_points),
            joinedload(Provider.entity)
            .selectinload(Entity.photos),
            joinedload(Provider.entity)
            .selectinload(Entity.categories)
            .joinedload(EntityCategory.category),
        )
        .filter(Provider.slug == slug)
        .first()
    )


def category_label_for(provider: Provider) -> str:
    """Prefer ENTITY taxonomy (``entity_categories`` → ``Category.name``), then
    ``category_ref``, then legacy ``category`` mapped through
    ``app.home.queries.CATEGORY_LABELS``.
    """
    ent = getattr(provider, "entity", None)
    if ent is not None and ent.categories:
        ordered = sorted(ent.categories, key=lambda ec: (not ec.is_primary, ec.id))
        for ec in ordered:
            cr = ec.category
            if cr is not None and getattr(cr, "name", None):
                return cr.name
    ref = getattr(provider, "category_ref", None)
    if ref is not None and getattr(ref, "name", None):
        return ref.name
    cat = provider.category
    if not cat:
        return "Local pro"
    if cat in CATEGORY_LABELS:
        return CATEGORY_LABELS[cat]
    if cat in LEGACY_PROVIDER_CATEGORY_LABELS:
        return LEGACY_PROVIDER_CATEGORY_LABELS[cat]
    return cat.replace("_", " ").capitalize()


_FRESH_DAYS = 30
_ACCEPTABLE_DAYS = 90
_AGING_DAYS = 180


def derive_freshness(
    provider: Provider, *, now: Optional[datetime] = None
) -> tuple[str, str]:
    """Return ``(band, copy)`` per UX spec §5 freshness-band table.

    Bands: ``fresh`` (≤30d), ``acceptable`` (≤90d), ``aging`` (≤180d),
    ``stale`` (>180d), ``none`` (no ``last_verified_at``).
    """
    if provider.last_verified_at is None:
        return ("none", "")
    now_dt = now or now_lake_havasu()
    last_verified = provider.last_verified_at
    if last_verified.tzinfo is None:
        last_verified = last_verified.replace(tzinfo=LAKE_HAVASU_TZ)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=LAKE_HAVASU_TZ)
    age_days = (now_dt - last_verified).days

    if age_days <= _FRESH_DAYS:
        # Cross-platform date format (no %-d / %#d).
        stamp = f"{last_verified.strftime('%B')} {last_verified.day}, {last_verified.year}"
        return ("fresh", f"Last verified {stamp}")
    if age_days <= _ACCEPTABLE_DAYS:
        months = max(1, age_days // 30)
        plural = "s" if months != 1 else ""
        return ("acceptable", f"Verified {months} month{plural} ago")
    if age_days <= _AGING_DAYS:
        return ("aging", "Verification may be outdated")
    return ("stale", "Business information may have changed")


def derive_hero_photo(provider: Provider) -> Optional[str]:
    """Hero URL: owner ``Photo`` (live + ``is_hero``) → pinned URL → Google."""
    ent = getattr(provider, "entity", None)
    if ent is not None:
        for photo in getattr(ent, "photos", None) or []:
            if photo.is_hero and photo.status == "live":
                if photo.hero_url:
                    return photo.hero_url
                break
    attrs = provider.attributes or {}
    pinned = attrs.get("hero_pin_photo_url")
    if pinned:
        return pinned
    photos = provider.google_photo_refs or []
    if photos:
        return photos[0]
    return None


def derive_gallery(
    provider: Provider, *, exclude_hero: bool = True
) -> list[str]:
    """Gallery URLs: owner live non-hero ``Photo`` rows (``display_order``), then Google.

    When ``exclude_hero`` is True, Google URLs matching the resolved hero URL
    are skipped; if a pinned hero is set, all Google refs are kept (legacy
    shape: pinned replaces hero without removing first Google ref).
    """
    out: list[str] = []
    ent = getattr(provider, "entity", None)
    if ent is not None:
        live_non_hero = sorted(
            (p for p in (getattr(ent, "photos", None) or []) if not p.is_hero),
            key=lambda p: p.display_order,
        )
        for p in live_non_hero:
            url = p.medium_url or p.cdn_url or p.thumbnail_url or p.hero_url
            if url:
                out.append(url)

    google = list(provider.google_photo_refs or [])
    attrs = provider.attributes or {}
    pinned = attrs.get("hero_pin_photo_url")
    hero_url = derive_hero_photo(provider) if exclude_hero else None
    for url in google:
        if exclude_hero and not pinned and hero_url is not None and url == hero_url:
            continue
        out.append(url)
    return out


def derive_directions_url(provider: Provider) -> Optional[str]:
    """Google Maps directions URL when we have an address or lat/lng.

    Prefers ``google_place_id`` (most stable), then address string, then
    lat/lng pair. Returns None when no location signal at all.
    """
    loc = getattr(getattr(provider, "entity", None), "location", None)
    place_id = None
    if loc is not None and loc.google_place_id:
        place_id = loc.google_place_id
    else:
        place_id = provider.google_place_id
    if place_id:
        return (
            f"https://www.google.com/maps/search/?api=1"
            f"&query={quote(provider.provider_name)}&query_place_id={quote(place_id)}"
        )
    addr = None
    if loc is not None and loc.address:
        addr = loc.address
    else:
        addr = provider.address
    if addr:
        return f"https://www.google.com/maps/search/?api=1&query={quote(addr)}"
    lat = loc.lat if loc is not None and loc.lat is not None else provider.lat
    lng = loc.lng if loc is not None and loc.lng is not None else provider.lng
    if lat is not None and lng is not None:
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
    return None


def derive_display_address(provider: Provider) -> Optional[str]:
    """Street / formatted address for profile display (non–service-area-only)."""
    loc = getattr(getattr(provider, "entity", None), "location", None)
    if loc is not None and loc.address:
        return loc.address
    return provider.address


_WEEKDAY_KEYS_STRUCT = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def _hours_rows_to_structured(rows: list[Hours]) -> dict[str, list[dict[str, str]]] | None:
    """Rebuild ``hours_structured`` JSON shape from ENTITY ``hours`` rows."""
    if not rows:
        return None
    buckets: dict[str, list[dict[str, str]]] = {k: [] for k in _WEEKDAY_KEYS_STRUCT}
    for h in rows:
        if h.day_of_week < 0 or h.day_of_week > 6:
            continue
        day_key = _WEEKDAY_KEYS_STRUCT[h.day_of_week]
        if h.opens_at is None or h.closes_at is None:
            buckets[day_key] = []
            continue
        buckets[day_key].append(
            {
                "open": h.opens_at.strftime("%H:%M"),
                "close": h.closes_at.strftime("%H:%M"),
            }
        )
    if not any(buckets.values()):
        return None
    return buckets


def effective_hours_structured(provider: Provider) -> dict | None:
    """Prefer ENTITY weekly ``hours`` rows when present; else legacy JSON column."""
    ent = getattr(provider, "entity", None)
    if ent is not None and ent.hours:
        rebuilt = _hours_rows_to_structured(list(ent.hours))
        if rebuilt is not None:
            return rebuilt
    hs = provider.hours_structured
    return hs if isinstance(hs, dict) else None


def derive_primary_phone_raw(provider: Provider) -> Optional[str]:
    """Phone digits/source string for ``_format_phone`` — ENTITY phone first."""
    ent = getattr(provider, "entity", None)
    if ent is not None and ent.contact_points:
        phones = [cp for cp in ent.contact_points if cp.kind == "phone"]
        phones.sort(key=lambda cp: (not cp.is_primary, cp.display_order, cp.id))
        if phones:
            return phones[0].value
    return provider.phone


def derive_website_url(provider: Provider) -> Optional[str]:
    """Primary website URL — ENTITY ``contact_points`` website kind, then legacy."""
    ent = getattr(provider, "entity", None)
    if ent is not None and ent.contact_points:
        sites = [cp for cp in ent.contact_points if cp.kind == "website"]
        sites.sort(key=lambda cp: (not cp.is_primary, cp.display_order, cp.id))
        if sites:
            return sites[0].value
    return provider.website


def derive_service_chips(provider: Provider) -> list[str]:
    """Build the service-detail chip row from ``provider.attributes``.

    Reads structured keys per UX spec §6 (emergency-service, by-appointment,
    licensed, accepts-insurance, sub-trade). Free-text keys are appended
    after structured ones. Returns an empty list when no signal is present.
    """
    attrs = provider.attributes or {}
    chips: list[str] = []
    if attrs.get("emergency_service"):
        chips.append("24/7 emergency")
    if attrs.get("by_appointment_only"):
        chips.append("By appointment")
    if attrs.get("licensed"):
        chips.append("Licensed")
    if attrs.get("accepts_insurance"):
        chips.append("Accepts insurance")
    sub_trades = attrs.get("sub_trades") or []
    if isinstance(sub_trades, list):
        chips.extend(str(s) for s in sub_trades if s)
    extra = attrs.get("service_chips") or []
    if isinstance(extra, list):
        chips.extend(str(s) for s in extra if s)
    return chips


def derive_service_area_only(provider: Provider) -> bool:
    """Per locked decision #4 (brief §6.4):
    - Explicit ``attributes.service_area_only`` always wins.
    - Otherwise: True when ``google_place_id`` is None (no commercial premise),
      False when set.
    """
    attrs = provider.attributes or {}
    if "service_area_only" in attrs:
        return bool(attrs.get("service_area_only"))
    return provider.google_place_id is None


def derive_service_area(provider: Provider) -> list[str]:
    """Return ``attributes.service_area`` as a list of strings (empty when absent)."""
    attrs = provider.attributes or {}
    raw = attrs.get("service_area") or []
    if isinstance(raw, list):
        return [str(s) for s in raw if s]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def derive_ask_hava_url(provider: Provider) -> str:
    """Construct ``/chat?q=...`` deep-link with a Hava-voiced prefill query.

    The ``/chat`` route currently does not consume ``q=`` for prefill —
    this is flagged in the brief §10 as a follow-up. The URL is built so
    the wiring lands without any view-model change.
    """
    q = f"Tell me about {provider.provider_name} in Lake Havasu City"
    return f"/chat?q={quote(q)}"


_WEEKDAY_KEYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _parse_hours_time(value: str) -> Optional[time]:
    """Parse ``"08:00"`` / ``"8:00 AM"`` / ``"17:30"`` into a ``time`` object."""
    if not value:
        return None
    text = value.strip().upper().replace(".", "")
    suffix = None
    if text.endswith("AM") or text.endswith("PM"):
        suffix = text[-2:]
        text = text[:-2].strip()
    try:
        if ":" in text:
            h_str, m_str = text.split(":", 1)
            hour = int(h_str)
            minute = int(m_str)
        else:
            hour = int(text)
            minute = 0
    except ValueError:
        return None
    if suffix == "PM" and hour < 12:
        hour += 12
    elif suffix == "AM" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)


def is_open_now(
    provider: Provider, *, now: Optional[datetime] = None
) -> tuple[Optional[bool], Optional[str]]:
    """Return ``(is_open, status_copy)`` based on ``hours_structured``.

    All time math runs in America/Phoenix (``LAKE_HAVASU_TZ``). Returns
    ``(None, None)`` when no parseable structured hours exist — caller
    template falls back to ``hours_freetext``.

    ``hours_structured`` shape (per existing seed data): ``{weekday:
    [{"open": "08:00", "close": "17:00"}, ...]}`` or ``None``. An empty
    list for a weekday means "closed today".
    """
    hours = effective_hours_structured(provider)
    if not hours or not isinstance(hours, dict):
        return (None, None)
    now_dt = now or now_lake_havasu()
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=LAKE_HAVASU_TZ)
    weekday_key = _WEEKDAY_KEYS[now_dt.weekday()]
    spans = hours.get(weekday_key)
    if spans is None:
        return (None, None)
    if not spans:
        return (False, "Closed today")
    now_t = now_dt.time()
    for span in spans:
        if not isinstance(span, dict):
            continue
        open_t = _parse_hours_time(str(span.get("open") or ""))
        close_t = _parse_hours_time(str(span.get("close") or ""))
        if open_t is None or close_t is None:
            continue
        if open_t <= now_t < close_t:
            close_label = _format_hour(close_t)
            return (True, f"Open now · Closes at {close_label}")
    # Past all spans for today — find the next opening within today's spans.
    upcoming = [
        _parse_hours_time(str(s.get("open") or ""))
        for s in spans
        if isinstance(s, dict)
    ]
    upcoming = [t for t in upcoming if t is not None and t > now_t]
    if upcoming:
        opens_t = min(upcoming)
        return (False, f"Closed · Opens at {_format_hour(opens_t)}")
    return (False, "Closed now")


def _format_hour(t: time) -> str:
    """Format a ``time`` as ``"5 PM"`` / ``"8:30 AM"`` — no leading zero."""
    suffix = "AM" if t.hour < 12 else "PM"
    h12 = t.hour % 12 or 12
    if t.minute:
        return f"{h12}:{t.minute:02d} {suffix}"
    return f"{h12} {suffix}"
