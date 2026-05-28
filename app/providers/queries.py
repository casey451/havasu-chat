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

from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import quote

from sqlalchemy.orm import Session, joinedload, selectinload

if TYPE_CHECKING:
    from app.providers.view_models import HavaCardViewModel

from app.core.timezone import LAKE_HAVASU_TZ, now_lake_havasu
from app.db.models import Entity, EntityCategory, Event, Hours, Provider
from app.home.queries import CATEGORY_LABELS, LEGACY_PROVIDER_CATEGORY_LABELS
from app.providers.photo_urls import google_photo_url


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
            joinedload(Provider.entity).joinedload(Entity.district),
            selectinload(Provider.events),
        )
        .filter(Provider.slug == slug)
        .first()
    )


# Lake Havasu seasonal windows (Phase 6.3 — tunable module constants).
_SEASON_SUMMER_START = (6, 1)
_SEASON_SUMMER_END = (9, 30)
_SEASON_FALL_START = (10, 1)
_SEASON_FALL_END = (10, 31)
_SEASON_WINTER_START = (11, 1)
_SEASON_WINTER_END = (4, 30)
_SEASON_SPRING_START = (5, 1)
_SEASON_SPRING_END = (5, 31)

_SEASON_STATUS_COPY: dict[str, str] = {
    "summer": "Summer hours (Jun 1 – Sep 30)",
    "fall": "Fall hours (Oct 1 – Oct 31)",
    "winter": "Winter hours (Nov 1 – Apr 30)",
    "spring": "Spring hours (May 1 – May 31)",
}


def _active_season_key_for_date(d: date) -> str:
    m, day = d.month, d.day

    def in_range(start_m: int, start_d: int, end_m: int, end_d: int) -> bool:
        start = (start_m, start_d)
        end = (end_m, end_d)
        cur = (m, day)
        if start <= end:
            return start <= cur <= end
        return cur >= start or cur <= end

    if in_range(*_SEASON_SUMMER_START, *_SEASON_SUMMER_END):
        return "summer"
    if in_range(*_SEASON_FALL_START, *_SEASON_FALL_END):
        return "fall"
    if in_range(*_SEASON_WINTER_START, *_SEASON_WINTER_END):
        return "winter"
    if in_range(*_SEASON_SPRING_START, *_SEASON_SPRING_END):
        return "spring"
    return "summer"


def _season_hours_rows(block: Any) -> dict | None:
    if not isinstance(block, dict):
        return None
    hours = block.get("hours")
    if isinstance(hours, dict) and hours:
        return hours
    overlay = block.get("hours_overlay")
    if isinstance(overlay, dict) and overlay:
        return overlay
    if any(k in block for k in _WEEKDAY_KEYS):
        return block
    return None


def effective_seasonal_hours(
    entity: Entity,
    *,
    now: Optional[datetime] = None,
) -> tuple[str | None, dict | None, str | None]:
    """Resolve active seasonal hours from ``entity.seasonal_hours`` JSON.

    Returns ``(season_name, hours_structured_dict, status_copy)`` or
    ``(None, None, None)`` when seasonal JSON is absent or the active season
    has no hours block — callers fall back to weekly / freetext hours.
    """
    raw = entity.seasonal_hours
    if raw is None:
        return (None, None, None)
    if not isinstance(raw, dict):
        return (None, None, None)

    now_dt = now or now_lake_havasu()
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=LAKE_HAVASU_TZ)
    season_key = _active_season_key_for_date(now_dt.date())
    block = raw.get(season_key)
    if block is None:
        return (None, None, None)
    rows = _season_hours_rows(block)
    if rows is None:
        return (None, None, None)
    copy = _SEASON_STATUS_COPY.get(season_key)
    if isinstance(block, dict):
        custom = block.get("status_copy") or block.get("label")
        if isinstance(custom, str) and custom.strip():
            copy = custom.strip()
    return (season_key, rows, copy)


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
        candidate = photos[0]
        if candidate.startswith("http://") or candidate.startswith("https://"):
            return candidate
        return google_photo_url(candidate)
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
        if url.startswith("http://") or url.startswith("https://"):
            resolved = url
        else:
            resolved = google_photo_url(url)
        if resolved is None:
            continue
        if exclude_hero and not pinned and hero_url is not None and resolved == hero_url:
            continue
        out.append(resolved)
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


def effective_hours_structured_from_entity(entity: Entity) -> dict | None:
    """Weekly hours dict from ENTITY ``hours`` rows (same shape as ``hours_structured``)."""
    rows = getattr(entity, "hours", None) or []
    if not rows:
        return None
    return _hours_rows_to_structured(list(rows))


def is_open_status_from_structured_hours(
    hours: dict | None, *, now: Optional[datetime] = None
) -> tuple[Optional[bool], Optional[str]]:
    """Return ``(is_open, status_copy)`` from structured weekly hours dict.

    Shared by :func:`is_open_now` (Provider) and :func:`is_open_status_for_entity`.
    """
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


def is_open_status_for_entity(
    entity: Entity, *, now: Optional[datetime] = None
) -> tuple[Optional[bool], Optional[str]]:
    """Open/closed copy for an ENTITY row using weekly ``hours`` extension."""
    return is_open_status_from_structured_hours(
        effective_hours_structured_from_entity(entity), now=now
    )


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
    return is_open_status_from_structured_hours(
        effective_hours_structured(provider), now=now
    )


def _format_hour(t: time) -> str:
    """Format a ``time`` as ``"5 PM"`` / ``"8:30 AM"`` — no leading zero."""
    suffix = "AM" if t.hour < 12 else "PM"
    h12 = t.hour % 12 or 12
    if t.minute:
        return f"{h12}:{t.minute:02d} {suffix}"
    return f"{h12} {suffix}"


EVENT_FRESHNESS_GREEN_DAYS = 7
EVENT_FRESHNESS_AMBER_DAYS = 21


def derive_event_freshness_band(event: Event, *, now: datetime) -> str:
    """Tighter decay for events: green <7d / amber 7-21d / red >21d from scrape anchor."""
    anchor = event.scraped_at
    if anchor is None:
        ent = event.entity
        anchor = ent.updated_at if ent is not None else event.created_at
    u = anchor
    if u.tzinfo is None:
        u = u.replace(tzinfo=UTC)
    n = now
    if n.tzinfo is None:
        n = n.replace(tzinfo=LAKE_HAVASU_TZ)
    days = max(0, (n - u).days)
    if days < EVENT_FRESHNESS_GREEN_DAYS:
        return "green"
    if days < EVENT_FRESHNESS_AMBER_DAYS:
        return "amber"
    return "red"


def derive_freshness_band_from_updated_at(
    updated_at: datetime, *, now: datetime
) -> str:
    """Phase 6 card freshness: green <30d / amber 30–90d / red >90d (``entities.updated_at``)."""
    u = updated_at
    if u.tzinfo is None:
        u = u.replace(tzinfo=UTC)
    n = now
    if n.tzinfo is None:
        n = n.replace(tzinfo=LAKE_HAVASU_TZ)
    days = max(0, (n - u).days)
    if days < 30:
        return "green"
    if days <= 90:
        return "amber"
    return "red"


def derive_hero_photo_from_entity(entity: Entity) -> Optional[str]:
    """Hero URL from live ENTITY ``Photo`` rows (``is_hero``), else None."""
    for photo in getattr(entity, "photos", None) or []:
        if photo.is_hero and photo.status == "live":
            return (
                photo.hero_url
                or photo.medium_url
                or photo.cdn_url
                or photo.thumbnail_url
            )
    return None


def _hero_photo_for_card(provider: Provider | None, entity: Entity) -> Optional[str]:
    if provider is not None:
        return derive_hero_photo(provider)
    return derive_hero_photo_from_entity(entity)


def _provider_is_sponsored_now(provider: Provider, *, now: datetime) -> bool:
    if (provider.tier or "") != "sponsored":
        return False
    until = provider.sponsored_until
    if until is None:
        return True
    if until.tzinfo is None and now.tzinfo is not None:
        return until > now.replace(tzinfo=None)
    return until > now


def _primary_category_for_entity(entity: Entity) -> tuple[str, str]:
    ecs = list(getattr(entity, "categories", None) or [])
    if not ecs:
        return ("local", "Local")
    ecs.sort(key=lambda ec: (not ec.is_primary, ec.id))
    cr = ecs[0].category
    if cr is not None and getattr(cr, "slug", None):
        return (str(cr.slug), str(cr.name or cr.slug))
    return ("local", "Local")


def _district_fields(entity: Entity) -> tuple[str, str]:
    dist = getattr(entity, "district", None)
    if dist is not None and getattr(dist, "slug", None):
        return (str(dist.slug), str(dist.name or dist.slug))
    return ("", "")


def _commercial_status_line_for_card(
    provider: Provider,
    freshness_band: str,
    *,
    now: datetime,
) -> tuple[str, str]:
    is_open, raw = is_open_now(provider, now=now)
    text = _commercial_card_status_line(is_open, raw)
    color = _commercial_status_line_color(freshness_band, is_open)
    return (text, color)


def _commercial_card_status_line(
    is_open: Optional[bool], raw: Optional[str]
) -> str:
    if raw is None or is_open is None:
        return "Hours unknown"
    if is_open:
        if raw and "Closes at" in raw:
            close_part = raw.split("Closes at", 1)[1].strip()
            return f"Open until {close_part}"
        return raw
    if raw and "Opens at" in raw:
        open_part = raw.split("Opens at", 1)[1].strip()
        return f"Closed; opens {open_part.lower()}"
    if raw:
        return raw.replace("Closed ·", "Closed;").replace(" · ", "; ")
    return "Hours unknown"


def _commercial_status_line_color(
    freshness_band: str, is_open: Optional[bool]
) -> str:
    if freshness_band == "red":
        return "red"
    if is_open is True:
        return "green"
    return "amber"


def _seasonal_hours_present(entity: Entity) -> bool:
    sh = entity.seasonal_hours
    if sh is None:
        return False
    if isinstance(sh, dict) and not sh:
        return False
    if isinstance(sh, list) and not sh:
        return False
    return True


def _place_status_line_for_card(
    entity: Entity, freshness_band: str, *, now: datetime
) -> tuple[str, str]:
    if freshness_band == "red":
        return ("Limited access", "red")
    if _seasonal_hours_present(entity):
        return ("Seasonal", "amber")
    is_open, _ = is_open_status_for_entity(entity, now=now)
    if is_open is True:
        return ("Open", "green")
    return ("Limited access", "amber")


def _event_status_line_for_card(
    event: Event, *, now: datetime, occurrence_date: date | None = None
) -> tuple[str, str]:
    if (event.status or "").strip().lower() == "cancelled":
        return ("Cancelled", "red")

    today = now.date()
    ev_date = occurrence_date if occurrence_date is not None else event.date
    days_ahead = (ev_date - today).days
    days_behind = (today - ev_date).days

    if ev_date == today:
        tlabel = _format_hour(event.start_time)
        return (f"Tonight at {tlabel.lower()}", "lake-blue")

    if days_ahead > 7:
        return (
            f"{ev_date.strftime('%b')} {ev_date.day}, {_format_hour(event.start_time).lower()}",
            "lake-blue",
        )

    if days_ahead > 0:
        if ev_date.weekday() >= 5:
            return ("This weekend", "lake-blue")
        return (f"This {ev_date.strftime('%A')}", "lake-blue")

    if days_behind > 7:
        return ("Last week", "red")

    if days_behind > 0:
        return ("Earlier this week", "amber")

    return (
        f"{ev_date.strftime('%b')} {ev_date.day}, {_format_hour(event.start_time).lower()}",
        "lake-blue",
    )


def _profile_url_for_card(
    entity: Entity,
    provider: Provider | None,
    event: Event | None,
) -> str:
    et = entity.entity_type or ""
    if et == "commercial" and provider and provider.slug:
        return f"/provider/{provider.slug}"
    if et == "event" and event is not None:
        return f"/events/{event.id}"
    return "/home"


def _heat_exposure_pill(entity: Entity) -> Optional[str]:
    hx = (entity.heat_exposure or "").strip()
    if not hx or hx == "indoor":
        return None
    return {
        "shaded": "Shaded",
        "outdoor": "Outdoor",
        "water_adjacent": "Water adjacent",
    }.get(hx, hx.replace("_", " ").title())


def build_card_view_model(
    db: Session,
    entity_id: str,
    *,
    now: Optional[datetime] = None,
) -> HavaCardViewModel | None:
    """Build a :class:`~app.providers.view_models.HavaCardViewModel` for any ENTITY row."""
    from app.providers.view_models import HavaCardViewModel

    now_dt = now or now_lake_havasu()
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=LAKE_HAVASU_TZ)

    entity = (
        db.query(Entity)
        .options(
            joinedload(Entity.location),
            joinedload(Entity.district),
            joinedload(Entity.categories).joinedload(EntityCategory.category),
            selectinload(Entity.hours),
            selectinload(Entity.photos),
        )
        .filter(Entity.id == entity_id)
        .first()
    )
    if entity is None:
        return None

    provider = (
        db.query(Provider).filter(Provider.entity_id == entity_id).first()
    )
    event = db.query(Event).filter(Event.entity_id == entity_id).first()

    freshness = derive_freshness_band_from_updated_at(entity.updated_at, now=now_dt)
    if entity.entity_type == "event" and event is not None:
        freshness = derive_event_freshness_band(event, now=now_dt)
    cat_slug, cat_label = _primary_category_for_entity(entity)
    d_slug, d_name = _district_fields(entity)

    et = entity.entity_type or "commercial"
    if et == "commercial" and provider is not None:
        status_text, status_color = _commercial_status_line_for_card(
            provider, freshness, now=now_dt
        )
        is_sponsored = _provider_is_sponsored_now(provider, now=now_dt)
    elif et == "place":
        status_text, status_color = _place_status_line_for_card(
            entity, freshness, now=now_dt
        )
        is_sponsored = False
    elif et == "event" and event is not None:
        status_text, status_color = _event_status_line_for_card(event, now=now_dt)
        is_sponsored = False
    else:
        is_open, _ = is_open_status_for_entity(entity, now=now_dt)
        status_text = "Hours unknown" if is_open is None else (
            "Open" if is_open else "Closed"
        )
        status_color = "red" if freshness == "red" else (
            "green" if is_open is True else "amber"
        )
        is_sponsored = bool(provider and _provider_is_sponsored_now(provider, now=now_dt))

    boat_badge = entity.boat_access is not None

    return HavaCardViewModel(
        entity_id=entity.id,
        entity_type=et if et in ("commercial", "place", "event") else "commercial",
        name=entity.name,
        profile_url=_profile_url_for_card(entity, provider, event),
        hero_photo_url=_hero_photo_for_card(provider, entity),
        category_slug=cat_slug,
        category_label=cat_label,
        district_slug=d_slug,
        district_name=d_name,
        status_line_text=status_text,
        status_line_color=status_color,
        freshness_band=freshness,
        is_sponsored=is_sponsored,
        boat_access_badge=boat_badge,
        heat_exposure_pill=_heat_exposure_pill(entity),
    )


def build_card_view_model_for_event_occurrence(
    db: Session,
    event_id: str,
    occurrence_date: date,
    *,
    now: Optional[datetime] = None,
) -> HavaCardViewModel | None:
    """Build a card for a specific occurrence date (recurring events)."""
    from app.providers.view_models import HavaCardViewModel

    now_dt = now or now_lake_havasu()
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=LAKE_HAVASU_TZ)

    event = db.query(Event).filter(Event.id == event_id).first()
    if event is None:
        return None

    entity = (
        db.query(Entity)
        .options(
            joinedload(Entity.location),
            joinedload(Entity.district),
            joinedload(Entity.categories).joinedload(EntityCategory.category),
            selectinload(Entity.hours),
            selectinload(Entity.photos),
        )
        .filter(Entity.id == event.entity_id)
        .first()
    )
    if entity is None:
        return None

    provider = (
        db.query(Provider).filter(Provider.entity_id == entity.id).first()
    )
    freshness = derive_event_freshness_band(event, now=now_dt)
    cat_slug, cat_label = _primary_category_for_entity(entity)
    d_slug, d_name = _district_fields(entity)
    status_text, status_color = _event_status_line_for_card(
        event, now=now_dt, occurrence_date=occurrence_date
    )

    return HavaCardViewModel(
        entity_id=entity.id,
        entity_type="event",
        name=entity.name,
        profile_url=_profile_url_for_card(entity, provider, event),
        hero_photo_url=_hero_photo_for_card(provider, entity),
        category_slug=cat_slug,
        category_label=cat_label,
        district_slug=d_slug,
        district_name=d_name,
        status_line_text=status_text,
        status_line_color=status_color,
        freshness_band=freshness,
        is_sponsored=False,
        boat_access_badge=entity.boat_access is not None,
        heat_exposure_pill=_heat_exposure_pill(entity),
    )
