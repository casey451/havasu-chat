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

from datetime import date, datetime, time, timedelta
from typing import Any, Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.timezone import now_lake_havasu
from app.db.models import Event, Program, Provider

# ─────────── helpers ───────────


def _format_phone(raw: str | None) -> tuple[str, str] | tuple[None, None]:
    """Return (display, raw_digits) or (None, None) when unusable."""
    if not raw:
        return None, None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
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
    """Best-available image URL for a provider, falling back to None.

    Note: ``google_photo_refs`` stores Places photo refs, not full URLs.
    Fetching the actual image is a separate call to Places' Photo API
    (deferred — see BUILD.md "Photography sourcing"). For now, we
    return None when there's no externally-fetchable URL, and the card
    falls back to its placeholder gradient.
    """
    return None  # placeholder until photo fetch is wired


def _hours_status(p: Provider, *, now: datetime) -> tuple[str, str]:
    """Return (status_class, status_text) for a Provider given current time.

    `status_class` ∈ {"open", "closed"}; `status_text` is short like
    "Open · until 6" or "Closed · opens 8 am".

    Reads ``Provider.google_hours`` (the most reliable, if present),
    then falls back to ``hours_structured``. When neither is parseable,
    returns ("closed", "Hours unknown") — kept short to avoid drawing
    eye into a non-fact.
    """
    # TODO(step 7.5): proper hours parsing. For step 2 we render a
    # static placeholder so the template doesn't crash on real data.
    return "open", "Hours on profile"


# ─────────── builders ───────────


def tonight(db: Session, *, limit: int = 3) -> list[dict[str, Any]]:
    """Today's events. The first slot is the feature card.

    Returns up to ``limit`` rows. Featured events sort first; the rest
    by ``start_time``. The first item gets ``feature: True`` so the
    template renders the big-card pattern.
    """
    today = now_lake_havasu().date()
    rows: list[Event] = (
        db.query(Event)
        .filter(Event.date == today, Event.status == "live")
        .order_by(Event.featured.desc(), Event.start_time.asc())
        .limit(limit)
        .all()
    )
    out: list[dict[str, Any]] = []
    for i, ev in enumerate(rows):
        when = _format_time(ev.start_time)
        meta = f"{ev.location_name} · {when}" if when else ev.location_name
        out.append(
            {
                "name": ev.title,
                "blurb": (ev.description or "").strip()[:180],
                "meta_text": meta,
                "footer_text": ev.location_name,
                "image_url": None,  # Event has no image surface yet
                "image_alt": ev.title,
                "url": f"/events/{ev.id}",
                "is_pick": bool(ev.featured) and i == 0,
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
        .order_by(Event.featured.desc(), Event.date.asc(), Event.start_time.asc())
        .limit(limit)
        .all()
    )
    out: list[dict[str, Any]] = []
    pick_used = False
    for ev in rows:
        is_pick = bool(ev.featured) and not pick_used
        if is_pick:
            pick_used = True
        when = _format_time(ev.start_time)
        weekday = ev.date.strftime("%A")
        meta = f"{weekday} · {when}" if when else weekday
        out.append(
            {
                "name": ev.title,
                "blurb": (ev.description or "").strip()[:180],
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
    Featured items rank above unfeatured at equal recency.
    """
    cutoff = now_lake_havasu() - timedelta(days=45)

    items: list[tuple[datetime, dict[str, Any]]] = []

    for ev in (
        db.query(Event)
        .filter(Event.created_at >= cutoff, Event.status == "live")
        .order_by(Event.featured.desc(), Event.created_at.desc())
        .limit(limit * 2)
        .all()
    ):
        items.append(
            (
                ev.created_at,
                {
                    "name": ev.title,
                    "blurb": (ev.description or "").strip()[:160],
                    "meta_text": "Event",
                    "footer_text": ev.location_name,
                    "image_url": None,
                    "image_alt": ev.title,
                    "url": f"/events/{ev.id}",
                    "is_pick": bool(ev.featured),
                    "is_business": False,
                    "dot": _category_dot(",".join(ev.tags or [])),
                },
            )
        )

    for pr in (
        db.query(Program)
        .filter(Program.created_at >= cutoff, Program.is_active.is_(True))
        .order_by(Program.featured.desc(), Program.created_at.desc())
        .limit(limit * 2)
        .all()
    ):
        items.append(
            (
                pr.created_at,
                {
                    "name": pr.title,
                    "blurb": (pr.description or "").strip()[:160],
                    "meta_text": "Program",
                    "footer_text": pr.location_name or pr.provider_name,
                    "image_url": None,
                    "image_alt": pr.title,
                    "url": f"/programs/{pr.id}",
                    "is_pick": bool(pr.featured),
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
        .order_by(Provider.featured.desc(), Provider.created_at.desc())
        .limit(limit * 2)
        .all()
    ):
        display, digits = _format_phone(prov.phone)
        status_class, status_text = _hours_status(prov, now=now_lake_havasu())
        items.append(
            (
                prov.created_at,
                {
                    "name": prov.provider_name,
                    "blurb": (prov.description or prov.featured_description or "").strip()[:160],
                    "meta_text": prov.category or "Local pro",
                    "footer_text": prov.address or "",
                    "image_url": _provider_image_url(prov),
                    "image_alt": prov.provider_name,
                    "url": f"/chat?q={prov.provider_name.replace(' ', '+')}",
                    "is_pick": bool(prov.featured),
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
    # Cap a single Hava's pick across the row to preserve signal.
    seen_pick = False
    out: list[dict[str, Any]] = []
    for _ts, item in items[: limit * 3]:
        if item["is_pick"]:
            if seen_pick:
                item = {**item, "is_pick": False}
            else:
                seen_pick = True
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
                "category": prov.category or "Local pro",
                "blurb": (prov.featured_description or prov.description or "").strip()[:180],
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
    """Pros & services pill row — top business categories by listing count.

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
        out.append(
            {
                "name": category,
                "query": f"find a {category.lower()}",
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
