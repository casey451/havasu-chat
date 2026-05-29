"""Home-page DB queries (BUILD.md step 2).

Each builder returns a list of dicts shaped to match the home template's
expectations (the same shape the mock_data builders produce). The Jinja
template is the contract; switching the data source is invisible to it.

Read posture: home is read-heavy and the queries are simple ORM SELECTs.
No caching here yet — that's stale-while-revalidate territory (step 4 for
the pullquote; if these queries become hot, similar treatment for the
rows).
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.timezone import now_lake_havasu
from app.db.models import Event, Program, Provider
from app.home.algorithmic_picks import (
    category_pick_index,
    new_on_hava_program_ranking,
    new_on_hava_provider_ranking,
    new_on_hava_ranking,
    this_week_ranking,
    tonight_ranking,
)
from app.providers.photo_urls import first_renderable_google_photo, google_photo_url

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
    "health-wellness-care": "Health, Wellness & Care",
    "eat-drink": "Eat & Drink",
    "on-the-water": "On the Water",
    "auto-rv-fuel": "Auto, RV & Fuel",
    "shopping-essentials": "Shopping, Grocery & Essentials",
    "outdoors-parks-trails": "Outdoors, Parks & Trails",
    "lodging-vacation-rentals": "Lodging & Vacation Rentals",
    "pets": "Pets",
    "events": "Events",
    "classes-sports-recreation": "Classes, Sports & Recreation",
    "public-civic-resources": "Public & Civic Resources",
}

LEGACY_PROVIDER_CATEGORY_LABELS: dict[str, str] = {
    # Bucket A + widened catalog / places strings → display aligned to new taxonomy.
    "health_medical": "Health, Wellness & Care",
    "food_drink": "Eat & Drink",
    "food": "Eat & Drink",
    "restaurant": "Eat & Drink",
    "bakery": "Eat & Drink",
    "home_services": "Home & Property Services",
    "general_contractor": "Home & Property Services",
    "plumbing": "Home & Property Services",
    "services": "Home & Property Services",
    "retail": "Shopping, Grocery & Essentials",
    "lake_recreation": "On the Water",
    "boat_repair": "On the Water",
    "boat_rental": "On the Water",
    "auto": "Auto, RV & Fuel",
    "lodging": "Lodging & Vacation Rentals",
    "pet": "Pets",
    "pets": "Pets",
    "veterinary": "Pets",
    "event_venue": "Events",
    "music": "Events",
    "recreation": "Classes, Sports & Recreation",
    "childcare_education": "Classes, Sports & Recreation",
    "education": "Classes, Sports & Recreation",
    "edu": "Classes, Sports & Recreation",
    "religion_community": "Public & Civic Resources",
    "fitness_sports": "Health, Wellness & Care",
    "fitness": "Health, Wellness & Care",
    "professional_services": "Professional",
    "beauty_personal_care": "Beauty & care",
    "real_estate": "Real estate",
    "insurance": "Insurance",
    "financial": "Financial",
    "legal": "Legal",
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
    "health_medical":        "find a doctor or clinic",
    "food_drink":            "where should I eat",
    "home_services":         "find a home pro",
    "retail":                "shops in Havasu",
    "lake_recreation":       "what's on the water today",
    "professional_services": "find a pro",
    "beauty_personal_care":  "salons and barbers",
    "auto":                  "auto repair in Havasu",
    "religion_community":    "community and worship",
    "fitness_sports":        "gyms and classes",
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
}

# ─────────── helpers ───────────

# Catches http(s) URLs, schemeless www.* URLs, and bare-domain fragments
# (lhcaz.gov/parks/foo) so descriptions copy-pasted from CMS exports get
# fully cleaned even when the protocol prefix was lost upstream.
_URL_RE = re.compile(
    r"(?:https?://|www\.)\S+"
    r"|\b\w+\.(?:com|gov|org|net|edu|io|us|co)(?:/\S*)?",
    re.IGNORECASE,
)

# Drops entire labelled-field lines that show up in scraped event blurbs:
#   "Date: May 9, 2026\nVenue: …\nOrganizer: …\nCategories: …"
# The labels themselves are surface-hostile — users read them as visible
# UI scaffolding, not as content. Strip pre-URL so we never leave a bare
# label on its own line.
_LABEL_LINE_RE = re.compile(
    r"^\s*(?:Date|Time|Venue|Address|Location|Organizer|"
    r"Categor(?:y|ies)|Tags?|Cost|Price|Phone|Website|URL|Link)"
    r"\s*:\s*.*$",
    re.IGNORECASE | re.MULTILINE,
)

# NANP-reserved placeholder range: (NXX) 555-01XX where NXX is any area code.
# These numbers are guaranteed-non-routable per FCC, and any of them in
# production data is a placeholder slip from seed/sample loading.
_PLACEHOLDER_PHONE_RE = re.compile(r"^\d{3}55501\d{2}$")


def _category_label(category: str | None) -> str:
    """Return the human-readable label for a Provider.category enum value.

    Falls back to a sentence-cased version of the slug when the category
    isn't in the canonical map (defensive — surface should never read
    ``general_contractor``). Empty/None returns ``"Local pro"`` so cards
    never render a blank meta line.

    Single source of truth for any provider/business surface that needs
    to display a category. The Jinja template must read from a builder-
    provided field that already contains the human label — never a raw
    ``Provider.category`` slug.

    See docs/maintainability/ui_data_correctness_spec.md §2.2.
    """
    if not category:
        return "Local pro"
    if category in CATEGORY_LABELS:
        return CATEGORY_LABELS[category]
    if category in LEGACY_PROVIDER_CATEGORY_LABELS:
        return LEGACY_PROVIDER_CATEGORY_LABELS[category]
    # Defensive fallback: replace underscores, sentence-case (not title-case
    # — "Real estate" reads better than "Real Estate" in surface meta).
    return category.replace("_", " ").capitalize()


def _card_blurb(event) -> str:
    """Extract a clean one-line blurb from an event/program/provider record.

    Sanitization order:

    1. Drop labelled-field lines (``Date:``, ``Venue:``, ``Organizer:``…)
       so scraped descriptions don't surface their own UI scaffolding.
    2. Strip URLs and bare-domain fragments — see ``_URL_RE``.
    3. Collapse whitespace; trim residual short trailing tokens that
       looked like URL remnants but didn't match the URL regex.
    4. Take the first sentence, truncate at 140 chars on a word boundary.

    Falls back to a venue+date sentence for Event-shaped records when
    sanitization produces an empty string — better than leaving a card
    with a blank body. Provider/Program records return empty as before.

    See docs/maintainability/ui_data_correctness_spec.md §4.2.
    """
    if getattr(event, "summary", None):
        return event.summary
    raw = (event.description or "").strip()
    raw = _LABEL_LINE_RE.sub("", raw)
    raw = _URL_RE.sub("", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    # Trim trailing 1–5 char alpha-only fragments that look like URL tails
    # the regex didn't catch ("Schedule at op" → "Schedule at"). Conservative:
    # only fires when preceded by whitespace and after we've already stripped
    # URLs, so legitimate short final words ("a", "I", "go") are rarely the
    # whole sentence at this point — they'd be inside a longer string.
    raw = re.sub(r"\s+[a-zA-Z]{1,5}$", "", raw).strip()
    if not raw:
        # Event-shaped fallback: venue + date is more useful than empty.
        loc = getattr(event, "location_name", None)
        ev_date = getattr(event, "date", None)
        if loc and ev_date is not None:
            try:
                # %-d is POSIX; on Windows / some libcs use lstrip("0").
                day = ev_date.strftime("%b ") + str(ev_date.day)
                return f"At {loc} on {day}"
            except (AttributeError, TypeError):
                return ""
        return ""
    first = raw.split(". ")[0].strip().rstrip(".")
    if len(first) > 140:
        first = first[:137].rsplit(" ", 1)[0] + "…"
    return first


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


def _format_time(t: time | None) -> str:
    if t is None:
        return ""
    h12 = t.hour % 12 or 12
    suffix = "am" if t.hour < 12 else "pm"
    if t.minute:
        return f"{h12}:{t.minute:02d} {suffix}"
    return f"{h12} {suffix}"


def _meta_line_for_event(ev: Event, *, today: date) -> str:
    when = _format_time(ev.start_time)
    if ev.date == today:
        return f"Today · {when}".strip(" ·")
    weekday = ev.date.strftime("%A")
    return f"{weekday} · {when}".strip(" ·")


def _category_dot(category: str | None) -> str:
    """Mostly-aesthetic flag mapping a category to teal/warm/live dot.

    Festivals, food, and time-of-day cues lean warm; everything else teal.
    Keeps the row visually mixed without monochrome fatigue. Rules of
    thumb, not exhaustive — drop into accent (teal) when in doubt.
    """
    if not category:
        return "accent"
    c = category.lower()
    if any(k in c for k in ("festival", "music", "food", "restaurant", "bar", "cafe")):
        return "warm"
    if "live" in c:
        return "live"
    return "accent"


def _provider_image_url(p: Provider) -> str | None:
    """Best-available image URL from Google photo columns.

    ``google_photo_urls`` and guarded http(s) entries in ``google_photo_refs``
    are returned first via :func:`first_renderable_google_photo`. Raw Places
    photo refs are upgraded to renderable Photo Media URLs via
    :func:`google_photo_url` so they become usable instead of dropped.
    Returns ``None`` only when no candidate yields a URL.
    """
    url = first_renderable_google_photo(p)
    if url:
        return url
    for candidate in p.google_photo_refs or []:
        if not isinstance(candidate, str):
            continue
        if candidate.startswith("http://") or candidate.startswith("https://"):
            continue
        # Raw Places ref — upgrade via the PR #37 helper. Returns None
        # when no API key is configured; fall through to next candidate.
        url = google_photo_url(candidate)
        if url:
            return url
    return None


_CLOSING_SOON_MINUTES = 30


def _minutes_until_close(
    hours: dict | None, *, now: datetime
) -> int | None:
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
            delta_minutes = (
                close_t.hour * 60 + close_t.minute
            ) - (now_t.hour * 60 + now_t.minute)
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
        minutes_left = _minutes_until_close(
            effective_hours_structured(p), now=now
        )
        if minutes_left is not None and minutes_left <= _CLOSING_SOON_MINUTES:
            return "closing-soon", status_copy or "Closing soon"
        return "open", status_copy or "Open now"
    return "closed", status_copy or "Closed now"


# ─────────── builders ───────────


def tonight_or_today_label(now: datetime) -> str:
    """Return ``"Tonight"`` after 4 PM local, otherwise ``"Today"``.

    The home row's heading switches with the time of day so the surface
    never reads "Tonight" at 8 AM. See spec §1.2(b).
    """
    return "Tonight" if now.hour >= 16 else "Today"


def _tonight_effective_floor(now: datetime) -> time:
    """Lower-bound on ``Event.start_time`` for the *Tonight/Today* row.

    Always drops past events for today (no 5 AM lap swim at noon). During
    the evening band (≥ 16:00) clamps the floor to at least 4 PM so the
    row reads as "evening events." See spec §1.2(a).
    """
    floor = now.time()
    if now.hour >= 16:
        floor = max(floor, time(16, 0))
    return floor


def tonight(db: Session, *, limit: int = 3) -> list[dict[str, Any]]:
    """Today's events with a time-of-day floor and venue de-dup.

    Drops events whose ``start_time`` is in the past so the row always
    reads forward. After 4 PM the floor clamps to 16:00 so the row reads
    as "evening." Soft-deduplicates by ``location_name`` so a single
    venue can't dominate (3× fetch, then walk one-per-location, backfill
    from rejects when only one venue has events today). The first
    surviving item gets ``feature: True``.

    Caller is expected to pull the heading via ``tonight_or_today_label``;
    this builder keeps its list-of-dicts return shape unchanged so
    existing callers don't need edits. See spec §1.2.
    """
    now = now_lake_havasu()
    today = now.date()
    floor = _tonight_effective_floor(now)
    candidates: list[Event] = (
        db.query(Event)
        .filter(
            Event.date == today,
            Event.status == "live",
            or_(
                Event.start_time.is_(None),
                Event.start_time >= floor,
            ),
        )
        .order_by(*tonight_ranking())
        .limit(limit * 3)
        .all()
    )
    seen_locations: set[str] = set()
    selected: list[Event] = []
    rejected: list[Event] = []
    for ev in candidates:
        loc_key = ev.location_name or ""
        if loc_key and loc_key in seen_locations:
            rejected.append(ev)
            continue
        if loc_key:
            seen_locations.add(loc_key)
        selected.append(ev)
        if len(selected) >= limit:
            break
    if len(selected) < limit:
        for ev in rejected:
            selected.append(ev)
            if len(selected) >= limit:
                break
    rows = selected
    pick_idx = category_pick_index(rows)
    out: list[dict[str, Any]] = []
    for i, ev in enumerate(rows):
        when = _format_time(ev.start_time)
        meta = f"{ev.location_name} · {when}" if when else ev.location_name
        out.append(
            {
                "name": ev.title,
                "blurb": _card_blurb(ev),
                "meta_text": meta,
                "footer_text": ev.location_name,
                "image_url": None,  # Event has no image surface yet
                "image_alt": ev.title,
                "url": f"/events/{ev.id}",
                "is_pick": pick_idx is not None and i == pick_idx,
                "feature": i == 0,
                "dot": _category_dot(",".join(ev.tags or [])),
            }
        )
    return out


def this_week(db: Session, *, limit: int = 3) -> list[dict[str, Any]]:
    """Events Friday–Sunday (or next 4 days), one Hava's pick max."""
    today = now_lake_havasu().date()
    end = today + timedelta(days=7)
    rows: list[Event] = (
        db.query(Event)
        .filter(
            Event.date > today,
            Event.date <= end,
            Event.status == "live",
        )
        .order_by(*this_week_ranking())
        .limit(limit)
        .all()
    )
    pick_idx = category_pick_index(rows)
    out: list[dict[str, Any]] = []
    for i, ev in enumerate(rows):
        is_pick = pick_idx is not None and i == pick_idx
        when = _format_time(ev.start_time)
        weekday = ev.date.strftime("%A")
        meta = f"{weekday} · {when}" if when else weekday
        out.append(
            {
                "name": ev.title,
                "blurb": _card_blurb(ev),
                "meta_text": meta,
                "footer_text": ev.location_name,
                "image_url": None,
                "image_alt": ev.title,
                "url": f"/events/{ev.id}",
                "is_pick": is_pick,
                "dot": _category_dot(",".join(ev.tags or [])),
            }
        )
    return out


def this_week_total(db: Session) -> int:
    today = now_lake_havasu().date()
    end = today + timedelta(days=7)
    return (
        db.query(Event)
        .filter(
            Event.date > today,
            Event.date <= end,
            Event.status == "live",
        )
        .count()
    )


def new_on_hava(db: Session, *, limit: int = 3) -> list[dict[str, Any]]:
    """Recently added catalog items — mix of providers, events, programs.

    Picks the most-recent N by ``created_at`` across the three tables.
    ``featured`` only affects which card gets the pick badge, not sort order.
    """
    cutoff = now_lake_havasu() - timedelta(days=45)

    items: list[tuple[datetime, dict[str, Any]]] = []

    for ev in (
        db.query(Event)
        .filter(Event.created_at >= cutoff, Event.status == "live")
        .order_by(*new_on_hava_ranking())
        .limit(limit * 2)
        .all()
    ):
        items.append(
            (
                ev.created_at,
                bool(ev.featured),
                {
                    "name": ev.title,
                    "blurb": _card_blurb(ev),
                    "meta_text": "Event",
                    "footer_text": ev.location_name,
                    "image_url": None,
                    "image_alt": ev.title,
                    "url": f"/events/{ev.id}",
                    "is_pick": False,
                    "is_business": False,
                    "dot": _category_dot(",".join(ev.tags or [])),
                },
            )
        )

    for pr in (
        db.query(Program)
        .filter(Program.created_at >= cutoff, Program.is_active.is_(True))
        .order_by(*new_on_hava_program_ranking())
        .limit(limit * 2)
        .all()
    ):
        items.append(
            (
                pr.created_at,
                bool(pr.featured),
                {
                    "name": pr.title,
                    "blurb": _card_blurb(pr),
                    "meta_text": "Program",
                    "footer_text": pr.location_name or pr.provider_name,
                    "image_url": None,
                    "image_alt": pr.title,
                    "url": f"/programs/{pr.id}",
                    "is_pick": False,
                    "is_business": False,
                    "dot": "warm",
                },
            )
        )

    for prov in (
        db.query(Provider)
        .filter(
            Provider.created_at >= cutoff,
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
        )
        .order_by(*new_on_hava_provider_ranking())
        .limit(limit * 2)
        .all()
    ):
        display, digits = _format_phone(prov.phone)
        status_class, status_text = _hours_status(prov, now=now_lake_havasu())
        items.append(
            (
                prov.created_at,
                bool(prov.featured),
                {
                    "name": prov.provider_name,
                    "blurb": _card_blurb(prov),
                    "meta_text": _category_label(prov.category),
                    "footer_text": prov.address or "",
                    "image_url": _provider_image_url(prov),
                    "image_alt": prov.provider_name,
                    "url": f"/chat?q={prov.provider_name.replace(' ', '+')}",
                    "is_pick": False,
                    "is_business": True,
                    "phone": display,
                    "phone_raw": digits,
                    "status": status_class,
                    "status_text": status_text,
                    "dot": _category_dot(prov.category),
                },
            )
        )

    items.sort(key=lambda pair: pair[0], reverse=True)
    merged = items[: limit * 3]
    pick_idx = category_pick_index(
        [SimpleNamespace(featured=featured) for _ts, featured, _item in merged]
    )
    out: list[dict[str, Any]] = []
    for i, (_ts, _featured, item) in enumerate(merged):
        if pick_idx is not None and i == pick_idx:
            item = {**item, "is_pick": True}
        out.append(item)
        if len(out) >= limit:
            break
    return out


def spotlights(db: Session, *, limit: int = 3) -> list[dict[str, Any]]:
    """Local pros row — paid spotlight placement.

    Sources from ``Provider.tier = 'spotlight' AND sponsored_until > now()``.
    See BUILD.md "Spotlight architecture" for the full disclosure
    contract; this builder only fetches data.
    """
    now = now_lake_havasu()
    rows: list[Provider] = (
        db.query(Provider)
        .filter(
            Provider.tier == "spotlight",
            or_(Provider.sponsored_until.is_(None), Provider.sponsored_until > now),
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
        )
        .order_by(Provider.created_at.desc())
        .limit(limit)
        .all()
    )
    out: list[dict[str, Any]] = []
    for prov in rows:
        display, digits = _format_phone(prov.phone)
        status_class, status_text = _hours_status(prov, now=now)
        out.append(
            {
                "name": prov.provider_name,
                "category": _category_label(prov.category),
                "blurb": _card_blurb(prov),
                "image_url": _provider_image_url(prov),
                "image_alt": prov.provider_name,
                "phone": display or "",
                "phone_raw": digits or "",
                "status": status_class,
                "status_text": status_text,
                "url": f"/chat?q={prov.provider_name.replace(' ', '+')}",
                "dot": _category_dot(prov.category),
            }
        )
    return out


def categories(db: Session) -> list[dict[str, Any]]:
    """Pros & services pill row -- top business categories by listing count.

    Pulls distinct ``Provider.category`` values, ranked by count. Static
    fallback when the catalog is too small or empty (early-stage Postgres
    states); same shape as the mocked categories so the template doesn't
    care.
    """
    from sqlalchemy import func as sa_func

    rows = (
        db.query(Provider.category, sa_func.count(Provider.id).label("n"))
        .filter(
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
            Provider.category.isnot(None),
        )
        .group_by(Provider.category)
        .order_by(sa_func.count(Provider.id).desc())
        .limit(10)
        .all()
    )
    if not rows:
        return _fallback_categories()
    out: list[dict[str, Any]] = []
    for category, _n in rows:
        human_name = _category_label(category)
        human_query = CATEGORY_QUERIES.get(category, f"find a {human_name.lower()}")
        out.append(
            {
                "name": human_name,
                "query": human_query,
                "warm": _category_dot(category) == "warm",
            }
        )
    return out


def _fallback_categories() -> list[dict[str, Any]]:
    """Static category list for an empty/early catalog. Same shape as live.

    Mirrors the mocked list in app.home.mock_data so the visual is
    stable when the DB hasn't been populated yet.
    """
    return [
        {"name": "Plumbers", "query": "find a plumber"},
        {"name": "Electricians", "query": "find an electrician"},
        {"name": "HVAC", "query": "find HVAC service"},
        {"name": "Pool service", "query": "pool service in Havasu"},
        {"name": "Contractors", "query": "find a contractor"},
        {"name": "Restaurants", "query": "where should I eat", "warm": True},
        {"name": "Cleaning", "query": "house cleaning service"},
        {"name": "Auto", "query": "auto repair in Havasu"},
        {"name": "Junk removal", "query": "junk removal"},
        {"name": "Salons", "query": "hair salons in Havasu"},
    ]
