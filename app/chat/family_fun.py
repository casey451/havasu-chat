"""Family / kids venue browse — deterministic Tier 2 path.

"What is there for kids?" was answering with whatever rows happened to match
keywords (usually just the Aquatic Center) and leaving out the arcade, bowling,
the parks, the skate park, the roller rink, and the RC track. This module owns
a curated, catalog-backed answer for that query shape: a structured
``business_list`` of family venues, plus a foot link to the Things to Do page.

Detection is conservative: the query must carry BOTH a kid/family token AND a
browse shape ("things to do", "what can we do", "activities", "fun", …).
Factual lookups ("aquatic center hours") never reach this — Tier 1 runs first
and the detector requires the browse shape.

The venue set is matched against live ``Provider`` rows (``is_active``,
``draft=False`` — the standard visibility gate), so a venue that isn't in the
catalog yet simply doesn't render; nothing is fabricated.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import Provider

logger = logging.getLogger(__name__)

# Kid/family audience token — word-boundary so "skids" never matches.
_KID_TOKEN_RE = re.compile(
    r"\b(kids?|children|child|toddlers?|teens?|teenagers?|family|families|"
    r"kid[- ]friendly|family[- ]friendly|young\s+ones?|little\s+ones?)\b",
    re.IGNORECASE,
)

# Browse shape — the user is asking for options, not a fact about one place.
_BROWSE_SHAPE_RE = re.compile(
    r"\b(things?\s+to\s+do|what\s+(?:is|are)\s+there|what\s+can|what\s+should|"
    r"anything\s+(?:for|to\s+do)|activities|options|stuff\s+to\s+do|"
    r"fun\s+(?:things|stuff|places|spots)?|places?\s+(?:for|to\s+take)|"
    r"where\s+(?:can|should)\s+(?:i|we)\s+take|entertain|keep\s+.{0,20}busy|"
    r"to\s+do\s+with)\b",
    re.IGNORECASE,
)

# Google primary categories that are family-fun venues.
_FAMILY_GOOGLE_CATEGORIES: tuple[str, ...] = (
    "amusement_park",
    "amusement_center",
    "bowling_alley",
    "arcade",
    "video_arcade",
    "movie_theater",
    "park",
    "playground",
    "tourist_attraction",
    "aquarium",
    "zoo",
    "water_park",
    "skate_park",
    "roller_skating_rink",
    "ice_skating_rink",
    "mini_golf_course",
    "trampoline_park",
)

# Name keywords for venues whose google category is generic
# (entertainment_attractions etc.) — the Havasu family-fun staples.
_FAMILY_NAME_KEYWORDS: tuple[str, ...] = (
    "arcade",
    "bowling",
    "lanes",
    "trampoline",
    "skate",
    "skating",
    "roller",
    "aquatic",
    "splash",
    "mini golf",
    "miniature golf",
    "rc ",
    "r/c",
    "rc club",
    "rc track",
    "laser tag",
    "playground",
)

# Never family-fun, whatever the keyword match says. Categories are matched
# as substrings of the category fields; names only against the flagrant set
# (so "Sandbar Mini Golf" isn't collateral damage of a bare "bar" needle).
_EXCLUDE_CATEGORY_TOKENS: tuple[str, ...] = (
    "bar",
    "night_club",
    "nightclub",
    "casino",
    "liquor",
    "brewery",
    "winery",
    "tobacco",
    "vape",
    "cannabis",
)
_EXCLUDE_NAME_TOKENS: tuple[str, ...] = (
    "casino",
    "liquor",
    "cannabis",
    "vape",
    "21+",
)

_MAX_ITEMS = 8


def is_family_browse_query(query: str) -> bool:
    """True when the query asks for kid/family activity options."""
    q = (query or "").strip()
    if not q:
        return False
    return bool(_KID_TOKEN_RE.search(q)) and bool(_BROWSE_SHAPE_RE.search(q))


def _is_excluded(p: Provider) -> bool:
    cats = " ".join(
        str(v or "").lower() for v in (p.google_primary_category, p.category)
    )
    if any(tok in cats for tok in _EXCLUDE_CATEGORY_TOKENS):
        return True
    name = str(p.provider_name or "").lower()
    return any(tok in name for tok in _EXCLUDE_NAME_TOKENS)


def family_fun_rows(db: Session, *, limit: int = _MAX_ITEMS) -> list[dict[str, Any]]:
    """Live family-fun provider rows, best-rated first. Never raises."""
    from app.chat.tier2_db_query import _provider_dict

    try:
        name_clauses = [
            Provider.provider_name.ilike(f"%{kw}%") for kw in _FAMILY_NAME_KEYWORDS
        ]
        cat_clauses = [
            Provider.google_primary_category == c for c in _FAMILY_GOOGLE_CATEGORIES
        ]
        candidates = (
            db.query(Provider)
            .filter(
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
                or_(*name_clauses, *cat_clauses),
            )
            .all()
        )
    except Exception:
        logger.exception("family_fun: provider query failed")
        return []

    keep = [p for p in candidates if not _is_excluded(p)]
    keep.sort(
        key=lambda p: (
            -(float(p.google_rating) if p.google_rating is not None else -1.0),
            str(p.provider_name or ""),
        )
    )
    return [_provider_dict(p) for p in keep[:limit]]


def try_family_fun(
    query: str,
    db: Session,
    component_meta: dict | None,
) -> str | None:
    """Voice line + ``business_list`` component for a family browse query.

    Returns ``None`` (caller falls through to the conversational tiers) when
    the query isn't a family browse or fewer than 2 venues are live.
    """
    if not is_family_browse_query(query):
        return None
    rows = family_fun_rows(db)
    if len(rows) < 2:
        return None

    from app.chat.component_builders import build_business_list

    payload = build_business_list(
        rows,
        category="family fun spot",
        total_count=len(rows),
        limit=_MAX_ITEMS,
    )
    payload["foot_link"] = "/categories/things-to-do-and-attractions"
    payload["foot_label"] = "All things to do →"
    if component_meta is not None:
        component_meta["type"] = "business_list"
        component_meta["data"] = payload

    n = len(rows)
    return (
        f"Plenty for kids here — {n} spots below. "
        "The full Things to Do page has the rest."
    )
