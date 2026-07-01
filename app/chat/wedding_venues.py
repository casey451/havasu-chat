"""Wedding / event-venue browse — deterministic curated answer.

"wedding venues" used to fall through to Tier 3 and surface a *planner* (The
Wedding Specialist) plus a mountain park — never the actual venues. This module
owns a curated, catalog-backed answer for the venue-shaped ask: a structured
``business_list`` of Lake Havasu's real wedding/event venues.

Mirrors :mod:`app.chat.family_fun`: the curated venue set is matched against
live ``Provider`` rows (``is_active``, ``draft=False`` — the standard visibility
gate) by EXACT normalized name, so the resorts' sub-venues ("Turtle Grille at
The Nautical…") never ride along and a venue that isn't live in the catalog
simply doesn't render. Nothing is fabricated.

Detection is conservative: the query must carry a wedding/event *venue* signal
("wedding venue", "reception hall", "place to get married") and must NOT be a
wedding *service* ask ("wedding planner / photographer / cake") — those are
different intents the directory answers elsewhere.

The venue set is verified marketed-for-weddings (2026-07-01 search N-audit item
2): London Bridge Resort, The Nautical Beachfront Resort, Iron Wolf Golf &
Country Club, Havasu Springs Resort, and the Quality Inn banquet space.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import Provider

logger = logging.getLogger(__name__)

# Venue signal — the user wants a PLACE to hold a wedding/reception/event.
_VENUE_SIGNAL_RE = re.compile(
    r"\b(wedding|weddings|reception|receptions|ceremony|ceremonies|banquet|"
    r"event)\s+(venue|venues|hall|halls|location|locations|space|spaces|site|sites)\b"
    r"|\b(banquet|reception)\s+halls?\b"
    r"|\bvenue\s+for\s+(?:a\s+)?(?:wedding|reception|ceremony|event|party)\b"
    r"|\b(?:place|spot|somewhere)\s+to\s+(?:get\s+married|hold\s+(?:a\s+)?(?:wedding|reception))\b"
    r"|\bget\s+married\b",
    re.IGNORECASE,
)

# Wedding SERVICE tokens — a planner/vendor ask, not a venue ask. Their presence
# means the venue handler must yield (the directory's service path owns them).
_SERVICE_TOKEN_RE = re.compile(
    r"\b(planner|planners|planning|coordinator|photographer|photography|"
    r"videographer|officiant|florist|flowers|cake|caterer|catering|dj|djs|"
    r"band|dress|dresses|tux|tuxedo|invitation|invitations|ring|rings|"
    r"registry|makeup|hair|rentals?)\b",
    re.IGNORECASE,
)

# Curated, web-verified Lake Havasu wedding/event venues (exact normalized names
# so sub-venues don't ride along). Havasu Springs Resort is real and marketed
# but currently has no active catalog row — it stays here so it renders the
# moment it's reactivated, and is omitted honestly until then.
_VENUE_NAMES: tuple[str, ...] = (
    "london bridge resort",
    "the nautical beachfront resort",
    "iron wolf golf & country club",
    "havasu springs resort",
    "quality inn & suites lake havasu city",
)

_MAX_ITEMS = 8


def _norm(name: str | None) -> str:
    return " ".join((name or "").lower().split())


def is_wedding_venue_query(query: str) -> bool:
    """True when the query asks for a wedding/event VENUE (not a vendor/service)."""
    q = (query or "").strip()
    if not q:
        return False
    if _SERVICE_TOKEN_RE.search(q):
        return False
    return bool(_VENUE_SIGNAL_RE.search(q))


def wedding_venue_rows(db: Session, *, limit: int = _MAX_ITEMS) -> list[dict[str, Any]]:
    """Live wedding-venue provider rows, best-rated first. Never raises.

    Matches the curated venue set by EXACT normalized name against active,
    non-draft rows, deduped to one row per venue (best-rated wins)."""
    from app.chat.tier2_db_query import _provider_dict

    try:
        name_clauses = [Provider.provider_name.ilike(n) for n in _VENUE_NAMES]
        candidates = (
            db.query(Provider)
            .filter(
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
                or_(*name_clauses),
            )
            .all()
        )
    except Exception:
        logger.exception("wedding_venues: provider query failed")
        return []

    allowed = set(_VENUE_NAMES)
    best: dict[str, Provider] = {}
    for p in candidates:
        key = _norm(p.provider_name)
        if key not in allowed:
            continue  # ILIKE is exact here, but re-validate defensively
        cur = best.get(key)
        if cur is None or (float(p.google_rating or -1.0) > float(cur.google_rating or -1.0)):
            best[key] = p

    kept = sorted(
        best.values(),
        key=lambda p: (
            -(float(p.google_rating) if p.google_rating is not None else -1.0),
            str(p.provider_name or ""),
        ),
    )
    return [_provider_dict(p) for p in kept[:limit]]


def try_wedding_venues(
    query: str,
    db: Session,
    component_meta: dict | None,
) -> str | None:
    """Voice line + ``business_list`` component for a wedding-venue query.

    Returns ``None`` (caller falls through to the conversational tiers) when the
    query isn't a venue ask or no curated venue is live in the catalog."""
    if not is_wedding_venue_query(query):
        return None
    rows = wedding_venue_rows(db)
    if not rows:
        return None

    from app.chat.component_builders import build_business_list

    payload = build_business_list(
        rows,
        category="wedding & event venue",
        total_count=len(rows),
        limit=_MAX_ITEMS,
        intent_query=query,
    )
    if component_meta is not None:
        component_meta["type"] = "business_list"
        component_meta["data"] = payload

    n = len(rows)
    place = "place" if n == 1 else "places"
    return (
        f"Here are {n} local {place} that host weddings and events — "
        "tap one for details, or ask about catering and dates."
    )
