"""Shared provider/category display helpers (formerly the home-page queries).

The pre-Sandstone home builders (tonight/this_week/new_on_hava/spotlights/
categories) were deleted 2026-07-02 — no route or template consumed them since
the Sandstone home landed; only their own tests kept them green. What remains
is the genuinely shared layer: CATEGORY_LABELS / LEGACY_PROVIDER_CATEGORY_LABELS
(the canonical slug->label maps) and the _format_phone/_hours_status/
_provider_image_url card helpers used by categories, providers, portal, and
chat surfaces.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.db.models import Provider
from app.providers.photo_urls import first_renderable_google_photo


def not_movie_event_clause() -> Any:
    """Lazy proxy for :func:`app.events.movie_tags.not_movie_event_clause`.

    Importing ``app.events.movie_tags`` at module load triggers
    ``app.events/__init__`` → ``events.queries`` → ``providers.queries`` → this
    module (a circular import). Deferring the import to call time breaks the
    cycle — everything is fully loaded by the time these feed queries run.
    """
    from app.events.movie_tags import not_movie_event_clause as _clause

    return _clause()


# ─────────── category labels & queries ───────────
#
# ``CATEGORY_LABELS`` — canonical **new-taxonomy** slugs (12) for Tier chips,
# enrichment CSV validation, and any surface keyed by ``Category.slug``.
# Order follows ``outputs/chatgpt_taxonomy_research_synthesis.md`` §1 (Tier 1,
# then Tier 2, then Tier 3).
#
# ``LEGACY_PROVIDER_CATEGORY_LABELS`` — free-text ``Provider.category`` /
# ``Program.activity_category`` strings still stored alongside ``category_id``
# until Phase 13; maps to human labels aligned with the audit memo
# (``docs/maintainability/category_backfill_mapping_audit_2026-05-14.md`` §2).

CATEGORY_LABELS: dict[str, str] = {
    "home-property-services": "Home & Property Services",
    "health-wellness-care": "Health & Medical",
    "eat-drink": "Eat & Drink",
    "on-the-water": "Lake Life",
    "auto-rv-fuel": "Auto, RV & Fuel",
    "shopping-essentials": "Shopping, Grocery & Essentials",
    "outdoors-parks-trails": "Outdoors, Parks & Trails",
    "lodging-vacation-rentals": "Lodging & Vacation Rentals",
    "pets": "Pets",
    "events": "Events",
    "classes-sports-recreation": "Fitness, Sports & Classes",
    "public-civic-resources": "Public & Civic Resources",
    "professional-services": "Professional Services",
}

LEGACY_PROVIDER_CATEGORY_LABELS: dict[str, str] = {
    # Bucket A + widened catalog / places strings → display aligned to new taxonomy.
    "health_medical": "Health & Medical",
    "food_drink": "Eat & Drink",
    "food": "Eat & Drink",
    "restaurant": "Eat & Drink",
    "bakery": "Eat & Drink",
    "home_services": "Home & Property Services",
    "general_contractor": "Home & Property Services",
    "plumbing": "Home & Property Services",
    "services": "Home & Property Services",
    "retail": "Shopping, Grocery & Essentials",
    "lake_recreation": "Lake Life",
    "boat_repair": "Lake Life",
    "boat_rental": "Lake Life",
    "auto": "Auto, RV & Fuel",
    "lodging": "Lodging & Vacation Rentals",
    "pet": "Pets",
    "pets": "Pets",
    "veterinary": "Pets",
    "event_venue": "Events",
    "music": "Events",
    "recreation": "Fitness, Sports & Classes",
    "childcare_education": "Fitness, Sports & Classes",
    "education": "Fitness, Sports & Classes",
    "edu": "Fitness, Sports & Classes",
    "religion_community": "Public & Civic Resources",
    "fitness_sports": "Health & Medical",
    "fitness": "Health & Medical",
    "professional_services": "Professional Services",
    "beauty_personal_care": "Beauty & care",
    "real_estate": "Professional Services",
    "insurance": "Professional Services",
    "financial": "Professional Services",
    "legal": "Professional Services",
    "tourism": "Tourism",
    "entertainment_attractions": "Attractions",
    "barbershop": "Barbershop",
    "uncategorized": "Uncategorized",
    "misc": "Miscellaneous",
    "other": "Other",
    "svc": "Service",
    "fun": "Fun",
    "bmx": "BMX",
    "bmxcaptest": "BMX",
    "onxcat": "Other",
    "space_pirates": "Other",
}

CATEGORY_QUERIES: dict[str, str] = {
    # what the chip submits to /chat — Hava-voiced, not slug-shaped
    "health_medical": "find a doctor or clinic",
    "food_drink": "where should I eat",
    "home_services": "find a home pro",
    "retail": "shops in Havasu",
    "lake_recreation": "what's on the water today",
    "professional_services": "find a pro",
    "beauty_personal_care": "salons and barbers",
    "auto": "auto repair in Havasu",
    "religion_community": "community and worship",
    "fitness_sports": "gyms and classes",
    # New-taxonomy slugs (forward-compatible if ``Provider.category`` ever stores them).
    "home-property-services": "find a home pro",
    "health-wellness-care": "find a doctor or clinic",
    "eat-drink": "where should I eat",
    "on-the-water": "what's on the water today",
    "auto-rv-fuel": "auto repair in Havasu",
    "shopping-essentials": "shops in Havasu",
    "outdoors-parks-trails": "parks and trails in Havasu",
    "lodging-vacation-rentals": "where to stay in Havasu",
    "pets": "pet services in Havasu",
    "events": "what's happening in Havasu",
    "classes-sports-recreation": "classes and recreation in Havasu",
    "public-civic-resources": "civic resources in Havasu",
    "professional-services": "find a pro",
}

# ─────────── helpers ───────────

# Catches http(s) URLs, schemeless www.* URLs, and bare-domain fragments
# (lhcaz.gov/parks/foo) so descriptions copy-pasted from CMS exports get
# fully cleaned even when the protocol prefix was lost upstream.
# Drops entire labelled-field lines that show up in scraped event blurbs:
#   "Date: May 9, 2026\nVenue: …\nOrganizer: …\nCategories: …"
# The labels themselves are surface-hostile — users read them as visible
# UI scaffolding, not as content. Strip pre-URL so we never leave a bare
# label on its own line.
# NANP-reserved placeholder range: (NXX) 555-01XX where NXX is any area code.
# These numbers are guaranteed-non-routable per FCC, and any of them in
# production data is a placeholder slip from seed/sample loading.
_PLACEHOLDER_PHONE_RE = re.compile(r"^\d{3}55501\d{2}$")




def _format_phone(raw: str | None) -> tuple[str, str] | tuple[None, None]:
    """Return (display, raw_digits) or (None, None) when unusable.

    Returns (None, None) for NANP-reserved 555-01XX placeholder numbers
    so they never render as a tappable tel: link. The card's footer
    falls back to "Phone on profile" or hides the phone row entirely
    (template responsibility).
    """
    if not raw:
        return None, None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if _PLACEHOLDER_PHONE_RE.match(digits):
        return None, None
    if len(digits) == 10:
        return f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}", digits
    return raw, digits or None





def _provider_image_url(p: Provider) -> str | None:
    """Best-available image URL from Google photo columns.

    Thin wrapper over :func:`first_renderable_google_photo`. As of the
    Track C photo-lane symmetry fix, the raw-ref upgrade (Places
    resource name → Photo Media URL via :func:`google_photo_url`) lives
    inside :func:`iter_renderable_google_photos`, so every call site —
    home, categories, provider profile — picks it up uniformly. Kept
    as a named helper so existing call sites (``new_on_hava`` row,
    spotlights row, category card resolver) read intent-first.
    """
    return first_renderable_google_photo(p)


_CLOSING_SOON_MINUTES = 30


def _minutes_until_close(hours: dict | None, *, now: datetime) -> int | None:
    """Return minutes until the current open span ends, or ``None``.

    Returns ``None`` when no parseable open span covers ``now`` (i.e.
    we're not currently open per the structured-hours data). Used to
    surface the ``closing-soon`` state inside ``_hours_status``.

    Mirrors the open-span scan in
    :func:`app.providers.queries.is_open_status_from_structured_hours`
    but returns the raw delta in minutes instead of an open/closed bool.
    """
    if not hours or not isinstance(hours, dict):
        return None
    # Use the same weekday keys as ``is_open_status_from_structured_hours``
    # so we read the same fields the existing helper reads. Mismatched keys
    # silently produced ``unknown`` for every Provider on the page until
    # this was caught -- see _hours_status smoke battery.
    from app.providers.queries import _WEEKDAY_KEYS, _parse_hours_time

    weekday_key = _WEEKDAY_KEYS[now.weekday()]
    spans = hours.get(weekday_key)
    if not spans:
        return None

    now_t = now.time()
    for span in spans:
        if not isinstance(span, dict):
            continue
        open_t = _parse_hours_time(str(span.get("open") or ""))
        close_t = _parse_hours_time(str(span.get("close") or ""))
        if open_t is None or close_t is None:
            continue
        if open_t <= now_t < close_t:
            delta_minutes = (close_t.hour * 60 + close_t.minute) - (now_t.hour * 60 + now_t.minute)
            return max(0, delta_minutes)
    return None


def _hours_status(p: Provider, *, now: datetime) -> tuple[str, str]:
    """Return ``(status_class, status_text)`` for a Provider.

    ``status_class`` is one of:

    - ``"open"`` — within hours, at least 30 minutes until close.
    - ``"closing-soon"`` — within 30 minutes of close.
    - ``"closed"`` — outside hours, with optional ``Opens at ...`` copy.
    - ``"unknown"`` — no parseable hours on file. The template must
      render plain meta text (``status_text``) without a status pill;
      see §B5.2 ("never show a pill we can't justify with data").

    Delegates to :func:`app.providers.queries.is_open_now`, which
    already handles seasonal-hours fallback, Phoenix-tz coercion, and
    span-by-span parsing of ``hours_structured``. This wrapper adds:

    1. The ``closing-soon`` state (not surfaced by ``is_open_now``).
    2. The ``unknown`` class for the no-data branch, replacing the
       prior placeholder that always rendered an ``open`` pill.

    Note: the spec also calls for an ``Provider.google_hours``
    fallback when ``hours_structured`` is empty; that's a separate
    workstream (it needs ``google_hours`` → ``hours_structured`` shape
    normalisation in ``effective_hours_structured`` itself, not here).
    Tracked under v1.5 inventory.
    """
    # Local import: ``app.providers.queries`` imports from ``app.db.models``,
    # not from this module, so this is safe — but the import is kept lazy so
    # ``app.home.queries`` stays cheap to import in non-render code paths.
    from app.providers.queries import effective_hours_structured, is_open_now

    is_open, status_copy = is_open_now(p, now=now)
    if is_open is None:
        # No parseable hours — surface as plain text, never as a pill.
        return "unknown", "Hours on profile"
    if is_open:
        minutes_left = _minutes_until_close(effective_hours_structured(p), now=now)
        if minutes_left is not None and minutes_left <= _CLOSING_SOON_MINUTES:
            return "closing-soon", status_copy or "Closing soon"
        return "open", status_copy or "Open now"
    return "closed", status_copy or "Closed now"
