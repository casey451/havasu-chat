"""Provider profile DB queries + derivations.

Pure-ish helpers consumed by ``app.providers.view_models.build``. Each
derive_* function takes a ``Provider`` and returns primitives so the
view-model layer can stay flat. Time-dependent helpers accept an
optional ``now`` argument for testability (matches the
``now_lake_havasu()`` injection pattern used elsewhere in the app).
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Optional
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.core.timezone import LAKE_HAVASU_TZ, now_lake_havasu
from app.db.models import Provider
from app.home.queries import CATEGORY_LABELS


def get_provider_by_slug(db: Session, slug: str) -> Optional[Provider]:
    """Return the active Provider with this slug, or None."""
    return db.query(Provider).filter(Provider.slug == slug).first()


def category_label_for(provider: Provider) -> str:
    """Prefer the structured ``category_ref.name`` when present; fall back to
    the legacy free-text ``category`` string mapped through
    ``app.home.queries.CATEGORY_LABELS``.
    """
    ref = getattr(provider, "category_ref", None)
    if ref is not None and getattr(ref, "name", None):
        return ref.name
    cat = provider.category
    if not cat:
        return "Local pro"
    if cat in CATEGORY_LABELS:
        return CATEGORY_LABELS[cat]
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
    """Hero-selection priority (UX spec §7 + locked decision #5):
    ``attributes.hero_pin_photo_url`` → first ``google_photo_refs`` → None.
    """
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
    """Return gallery photos beyond the hero. Pinned hero is excluded only
    when it appears in the underlying ``google_photo_refs`` list."""
    photos = list(provider.google_photo_refs or [])
    if not photos:
        return []
    if exclude_hero:
        attrs = provider.attributes or {}
        pinned = attrs.get("hero_pin_photo_url")
        if pinned:
            return photos
        # First photo is the hero — drop it.
        return photos[1:]
    return photos


def derive_directions_url(provider: Provider) -> Optional[str]:
    """Google Maps directions URL when we have an address or lat/lng.

    Prefers ``google_place_id`` (most stable), then address string, then
    lat/lng pair. Returns None when no location signal at all.
    """
    place_id = provider.google_place_id
    if place_id:
        return (
            f"https://www.google.com/maps/search/?api=1"
            f"&query={quote(provider.provider_name)}&query_place_id={quote(place_id)}"
        )
    if provider.address:
        return f"https://www.google.com/maps/search/?api=1&query={quote(provider.address)}"
    if provider.lat is not None and provider.lng is not None:
        return f"https://www.google.com/maps/search/?api=1&query={provider.lat},{provider.lng}"
    return None


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
    hours = provider.hours_structured
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
