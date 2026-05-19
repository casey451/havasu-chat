"""Multi-domain intent heuristics for cross-entity chat (Phase 7)."""

from __future__ import annotations

import re

# Nouns that imply a Tier-1 category slug (subset used in cross-entity tests).
_NOUN_TO_CATEGORY_SLUGS: dict[str, tuple[str, ...]] = {
    "dog": ("pets", "eat-drink", "outdoors-parks-trails"),
    "dogs": ("pets", "eat-drink", "outdoors-parks-trails"),
    "pet": ("pets",),
    "pets": ("pets",),
    "breakfast": ("eat-drink",),
    "brunch": ("eat-drink",),
    "coffee": ("eat-drink",),
    "cafe": ("eat-drink",),
    "restaurant": ("eat-drink",),
    "grocery": ("shopping-essentials",),
    "groceries": ("shopping-essentials",),
    "park": ("outdoors-parks-trails",),
    "parks": ("outdoors-parks-trails",),
    "trail": ("outdoors-parks-trails",),
    "trails": ("outdoors-parks-trails",),
    "hotel": ("lodging-vacation-rentals",),
    "lodging": ("lodging-vacation-rentals",),
    "plumber": ("home-property-services",),
    "vet": ("pets", "health-wellness-care"),
}

_CONNECTOR_RE = re.compile(
    r"\b(?:and|with|where\s+i\s+can\s+also|as\s+well\s+as)\b",
    re.IGNORECASE,
)


def detect_multi_domain_category_slugs(query: str) -> tuple[str, ...] | None:
    """Return category slugs when the query spans multiple domains, else None."""
    q = (query or "").lower()
    if not q.strip():
        return None

    hits: list[str] = []
    seen_slugs: set[str] = set()
    tokens = set(re.findall(r"[a-z']+", q))
    for noun, slugs in _NOUN_TO_CATEGORY_SLUGS.items():
        if noun in tokens or re.search(rf"\b{re.escape(noun)}\b", q):
            for slug in slugs:
                if slug not in seen_slugs:
                    seen_slugs.add(slug)
                    hits.append(slug)

    if len(hits) >= 2:
        return tuple(hits)

    if _CONNECTOR_RE.search(q) and len(hits) >= 1:
        # "groceries and coffee" — connector + at least one category noun.
        extra = [s for s in _infer_second_slug_from_connector(q) if s not in seen_slugs]
        combined = hits + extra
        if len(set(combined)) >= 2:
            return tuple(dict.fromkeys(combined))

    return None


def _infer_second_slug_from_connector(q: str) -> list[str]:
    """When a connector is present, scan both sides for category nouns."""
    out: list[str] = []
    for noun, slugs in _NOUN_TO_CATEGORY_SLUGS.items():
        if re.search(rf"\b{re.escape(noun)}\b", q):
            out.extend(slugs)
    return out


__all__ = ["detect_multi_domain_category_slugs"]
