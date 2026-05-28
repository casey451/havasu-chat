"""Fuzzy match user queries to a canonical ``Program.provider_name``."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Sequence

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat.normalizer import normalize
from app.db.models import Program, Provider

# Keys MUST match ``Program.provider_name`` / ``Provider.provider_name`` strings in the live catalog
# (contributions, River Scene imports, and operator edits).
CANONICAL_EXTRAS: dict[str, list[str]] = {
    "Iron Wolf Golf & Country Club": [
        "iron wolf",
        "iron wolf golf",
    ],
    "Altitude Trampoline Park — Lake Havasu City": [
        "altitude",
        "altitude trampoline park",
        "trampoline park",
    ],
    "Havasu Lanes": [
        "bowling alley",
        "havasu lanes",
    ],
    "Bridge City Combat (also: Bridge City Combat & Barry Sullins Jiu-Jitsu)": [
        "bridge city",
        "bridge city combat",
    ],
    "Lake Havasu City BMX": [
        "bmx",
        "lake havasu bmx",
        "bmx track",
        "sara park bmx",
    ],
    "Lake Havasu Mountain Bike Club": [
        "mountain bike",
        "mountain bikes",
        "mountain biking",
        "mtb",
        "bike trail",
        "dirt trail",
        "trail riding",
    ],
    "Universal Gymnastics and All Star Cheer — Sonics": [
        "sonics",
        "universal gymnastics",
        "gymnastics place on kiowa",
        # BACKLOG #52: smoke phrasing — fuzzy baseline alone stays blocked by substring guards.
        "allstar gym",
    ],
    "All Seasons Plumbing": [
        # BACKLOG #52: superlative open-ended phrasing shares tokens with this needle.
        "plumber in lake havasu",
    ],
    "Lake Havasu City Aquatic Center": [
        "aquatic center",
        "havasu aquatic center",
    ],
    "The Tap Room Jiu Jitsu": [
        "tap room",
        "tap room bjj",
        "tap room jiu jitsu",
    ],
    "Lake Havasu Little League": [
        "little league",
    ],
    "Havasu Lions FC": [
        "lions",
        "havasu lions",
    ],
    "Lake Havasu Black Belt Academy": [
        "black belt academy",
        "lhcbba",
    ],
    "Aqua Beginnings": [
        "aqua beginnings",
    ],
    "Ballet Havasu": [
        "ballet havasu",
    ],
    "Flips for Fun Gymnastics": [
        "flips for fun",
    ],
}


@dataclass(frozen=True)
class _EntityRow:
    """One provider with all phrases to score against (already lowercased / normalized)."""

    canonical: str
    needles: frozenset[str]
    # Lowercased Provider / Program category hints for Backlog #47 cross-category guard.
    category_blob: str = ""


@dataclass(frozen=True)
class EntityMatch:
    """One catalog provider mentioned in free text (Phase 6.4.1)."""

    name: str
    type: str
    id: str


_rows: list[_EntityRow] | None = None
# Monotonic timestamp of the last successful refresh_entity_matcher() call.
# Used by ensure_entity_matcher() to skip rebuilds within the TTL window.
_rows_loaded_at: float | None = None

# Catalog TTL (seconds). Override via env for tests / staging. Default 5 min
# matches the planning doc: cache hits drop the per-request rebuild cost from
# ~50-150ms to ~0ms while keeping fresh catalog edits visible within 5 minutes
# of an operator save.
_CATALOG_TTL_SECONDS = float(os.environ.get("ENTITY_MATCHER_CATALOG_TTL_S", "300"))

# Backlog #47: when the query names a trade (plumber, …) and the candidate row
# names an incompatible trade (BMX, …), location-token overlap must not win.
# Skip the guard when the user explicitly names the entity (distinctive tokens).
_LOCATION_QUERY_STOPWORDS: frozenset[str] = frozenset(
    {
        "lake",
        "havasu",
        "city",
        "arizona",
        "az",
        "the",
        "and",
        "for",
        "inn",
        "at",
        "our",
        "any",
        "all",
        "some",
        "best",
        "good",
        "top",
        "need",
        "find",
        "near",
        "around",
    }
)

_INCOMPATIBLE_TRADE_PAIRS: tuple[frozenset[str], ...] = (
    frozenset({"plumbing", "bmx"}),
    frozenset({"plumbing", "trampoline_park"}),
    frozenset({"electrical", "bmx"}),
    frozenset({"dental", "bmx"}),
    frozenset({"medical", "bmx"}),
    frozenset({"gymnastics_cheer", "bmx"}),
    frozenset({"gymnastics_cheer", "trampoline_park"}),
    frozenset({"gymnastics_cheer", "plumbing"}),
    frozenset({"gymnastics_cheer", "electrical"}),
    frozenset({"gymnastics_cheer", "dental"}),
    frozenset({"gymnastics_cheer", "medical"}),
)


def _trade_cluster_tags(blob: str) -> frozenset[str]:
    """Map free text to coarse trade tags for cross-category mismatch checks."""
    b = blob.lower()
    tags: set[str] = set()
    if re.search(r"\b(plumber|plumbing|plumbers)\b", b):
        tags.add("plumbing")
    if re.search(r"\b(electrician|electrical)\b", b):
        tags.add("electrical")
    if re.search(r"\b(dentist|dental|orthodont)\b", b):
        tags.add("dental")
    if re.search(r"\b(doctor|physician|clinic|medical)\b", b) and "veterinary" not in b:
        tags.add("medical")
    if re.search(r"\b(trampoline|trampoline park)\b", b) or (
        "altitude" in b and "trampoline" in b
    ):
        tags.add("trampoline_park")
    if re.search(r"\bbmx\b", b) or "bicycle motocross" in b:
        tags.add("bmx")
    if re.search(r"\b(restaurant|café|cafe|pizza|coffee shop|brewery|bar)\b", b):
        tags.add("food_service")
    if re.search(r"\bgymnastics\b", b) or re.search(r"\bgym\b", b):
        tags.add("gymnastics_cheer")
    if re.search(r"\bcheerleading\b", b) or re.search(r"\bcheer\b", b):
        tags.add("gymnastics_cheer")
    if re.search(r"\btumbling\b", b):
        tags.add("gymnastics_cheer")
    if re.search(r"\ball[\s-]?star\b", b) or re.search(r"\ballstar\b", b):
        tags.add("gymnastics_cheer")
    return frozenset(tags)


def _distinctive_entity_tokens(canonical: str) -> set[str]:
    return {
        t
        for t in re.split(r"\W+", canonical.lower())
        if len(t) >= 3 and t not in _LOCATION_QUERY_STOPWORDS
    }


def _query_explicitly_names_row(norm_query: str, row: _EntityRow) -> bool:
    """True when the user likely referred to this business by name (skip #47 guard)."""
    nq = norm_query.lower()
    for tok in _distinctive_entity_tokens(row.canonical):
        if tok in nq:
            return True
    for needle in row.needles:
        if len(needle) >= 8 and needle in nq:
            return True
    return False


def _row_supports_trade_intent(q_tags: frozenset[str], row_blob: str) -> bool:
    """True when row text/slug hints align with a trade-shaped query."""
    b = row_blob.lower()
    if "plumbing" in q_tags:
        return bool(
            re.search(r"\b(plumber|plumbing|plumbers|drain|sewer)\b", b) or "plumb" in b
        )
    if "electrical" in q_tags:
        return bool(
            re.search(r"\b(electrician|electrical|electric|wiring)\b", b)
            or "electric" in b
        )
    if "dental" in q_tags:
        return bool(re.search(r"\b(dentist|dental|orthodont)\b", b))
    if "medical" in q_tags:
        return bool(re.search(r"\b(doctor|physician|clinic|medical)\b", b))
    if "food_service" in q_tags:
        return bool(
            re.search(
                r"\b(restaurant|cafe|coffee|pizza|grill|kitchen|brewery|bar|diner)\b", b
            )
        )
    if "gymnastics_cheer" in q_tags:
        return bool(
            re.search(
                r"\b(gymnastics|gym|cheerleading|cheer|tumbling|all[\s-]?star|allstar)\b",
                b,
            )
        )
    return False


def _category_guard_skips_row(norm_query: str, row: _EntityRow) -> bool:
    """Drop a catalog row from fuzzy contention when trade intent mismatches the row.

    **BACKLOG #52 (trade-superlative bypass):** Lane 1's #47 guard drops rows when the
    query carries a trade-shaped intent but the candidate row does not *look* like that
    trade in ``category_blob`` / name tokens — blocking obvious cross-category false
    positives (plumber vs BMX). Open-ended trade queries ("best plumber", "find a gym")
    still need eligible **same-trade** rows to survive when both sides map to the same
    coarse ``_trade_cluster_tags`` bucket (explicit overlap check immediately below).

    **Does not re-open #47:** incompatible-trade pairs (e.g. ``plumbing`` + ``bmx`` on
    the same candidate union) still return ``True`` (skip) before fuzzy scoring — disjoint
    tags across query vs row still route through :data:`_INCOMPATIBLE_TRADE_PAIRS`.
    """
    if _query_explicitly_names_row(norm_query, row):
        return False
    q_tags = _trade_cluster_tags(norm_query)
    if not q_tags:
        return False
    row_blob = f"{row.category_blob} {row.canonical} {' '.join(row.needles)}"
    r_tags = _trade_cluster_tags(row_blob)
    # Same-trade alignment — never skip when tags overlap (#52).
    if q_tags & r_tags:
        return False
    if r_tags:
        union = q_tags | r_tags
        for pair in _INCOMPATIBLE_TRADE_PAIRS:
            if pair <= union:
                return True
        return False
    if _row_supports_trade_intent(q_tags, row_blob):
        return False
    return True


def _category_blob_for_canonical(db: Session, canonical: str) -> str:
    """Concatenate Provider + Program category hints for ``canonical``."""
    parts: list[str] = []
    prow = db.execute(
        select(Provider.category, Provider.google_primary_category).where(
            Provider.provider_name == canonical,
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
        ).limit(1)
    ).first()
    if prow is not None:
        cat, gcat = prow
        if cat:
            parts.append(cat.strip().lower())
        if gcat:
            parts.append(str(gcat).strip().lower())
    act_cats = db.scalars(
        select(Program.activity_category)
        .where(Program.provider_name == canonical)
        .distinct()
    ).all()
    for ac in act_cats:
        if ac:
            parts.append(str(ac).strip().lower())
    return " ".join(parts)


def _synthetic_category_blob(canonical: str, needles: frozenset[str]) -> str:
    """Category hints when matching against an explicit name list (no DB row)."""
    return f"{canonical.lower()} {' '.join(needles)}"


def _needles_for_canonical(canonical: str) -> frozenset[str]:
    out: set[str] = set()
    c = canonical.strip()
    if not c:
        return frozenset()
    out.add(normalize(c))
    out.add(c.lower())
    for extra in CANONICAL_EXTRAS.get(c, []):
        n = normalize(extra)
        if n:
            out.add(n)
    return frozenset(x for x in out if x)


def refresh_entity_matcher(db: Session) -> None:
    """Rebuild the in-memory index from ``Program.provider_name`` + active ``Provider`` rows.

    Performance: this function is hot - it runs at the start of every chat
    request via the callers in ``unified_router.py`` and ``halt3_validator.py``.
    The previous implementation issued 1 + 2*N DB queries (N ~= 2,200 canonical
    names -> ~4,400 round-trips, ~50-150ms tax per request). It now issues a
    fixed **4** queries regardless of catalog size: 2 to list distinct
    canonical names, plus 2 batch ``IN`` queries that load every
    ``Provider.category`` / ``Provider.google_primary_category`` and every
    distinct ``(provider_name, activity_category)`` row in one round-trip each.

    Two sources are unioned because the catalog has historical denormalization:

    - ``Program.provider_name`` is a denormalized string column populated by River Scene
      imports and contributions; some legacy rows may reference a name that has no
      matching Provider row (kept for backwards compatibility).
    - ``Provider`` is the unified provider table — both event-host providers and the
      Google Places business catalog (``google_place_id IS NOT NULL``) live here.
      Filtered to ``is_active=True`` and ``draft=False`` so half-completed contributions
      and deactivated rows don't surface in chat retrieval.

    CANONICAL_EXTRAS still applies to the 14 hand-curated program providers; Google
    business names use only normalized + lowercased forms as needles. Per-row scoring
    uses ``rapidfuzz.fuzz.token_set_ratio`` with threshold 75 (unchanged).
    """
    global _rows, _rows_loaded_at
    program_names = db.scalars(select(Program.provider_name).distinct()).all()
    provider_names = db.scalars(
        select(Provider.provider_name).where(
            Provider.is_active.is_(True), Provider.draft.is_(False)
        )
    ).all()
    canon = sorted(
        {(n or "").strip() for n in (*program_names, *provider_names) if (n or "").strip()}
    )
    blob_by_canonical = _category_blobs_for_canonicals(db, canon)
    _rows = [
        _EntityRow(c, _needles_for_canonical(c), blob_by_canonical.get(c, ""))
        for c in canon
    ]
    _rows_loaded_at = time.monotonic()


def _category_blobs_for_canonicals(
    db: Session, canonicals: Sequence[str]
) -> dict[str, str]:
    """Batched equivalent of :func:`_category_blob_for_canonical` for many names.

    Returns ``{canonical: " ".join(category_parts)}`` for every name in
    ``canonicals``. Names with no matching Provider row and no Program rows
    map to ``""`` (or are omitted; callers use ``.get(name, "")``).

    Two DB queries total - one for Provider category info, one for distinct
    Program activity_category per provider. Order within the blob mirrors the
    per-canonical version (Provider.category -> google_primary_category ->
    Program.activity_category) so :func:`_trade_cluster_tags` produces the
    same tag set regardless of whether the blob was built per-row or batched.
    """
    if not canonicals:
        return {}
    names = list(canonicals)
    parts_by_canon: dict[str, list[str]] = {c: [] for c in names}
    prows = db.execute(
        select(
            Provider.provider_name,
            Provider.category,
            Provider.google_primary_category,
        ).where(
            Provider.provider_name.in_(names),
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
        )
    ).all()
    # Per-canonical version only takes the first Provider row (LIMIT 1); replicate
    # that here so the resulting blob is byte-identical when a single Provider row
    # exists, and uses a deterministic "first-seen" pick when there are duplicates.
    seen_provider: set[str] = set()
    for name, cat, gcat in prows:
        if name in seen_provider:
            continue
        seen_provider.add(name)
        bucket = parts_by_canon.setdefault(name, [])
        if cat:
            bucket.append(str(cat).strip().lower())
        if gcat:
            bucket.append(str(gcat).strip().lower())
    act_rows = db.execute(
        select(Program.provider_name, Program.activity_category)
        .where(Program.provider_name.in_(names))
        .distinct()
    ).all()
    for name, ac in act_rows:
        if ac:
            parts_by_canon.setdefault(name, []).append(str(ac).strip().lower())
    return {c: " ".join(parts_by_canon.get(c, [])) for c in names}


def reset_entity_matcher() -> None:
    """Clear the cache (mainly for tests)."""
    global _rows, _rows_loaded_at
    _rows = None
    _rows_loaded_at = None


def _catalog_is_fresh() -> bool:
    """True when the in-memory catalog is loaded and within the TTL window."""
    if _rows is None or _rows_loaded_at is None:
        return False
    return (time.monotonic() - _rows_loaded_at) < _CATALOG_TTL_SECONDS


def ensure_entity_matcher(db: Session, *, force: bool = False) -> None:
    """Ensure the in-memory catalog is loaded and fresh; rebuild only if needed.

    Cheap call (~us) on the hot path when the catalog is already loaded and the
    TTL window has not expired. Pass ``force=True`` to rebuild unconditionally
    (used by the HALT 3 eval-set runner so each spec sees an up-to-date index).

    Callers that previously invoked :func:`refresh_entity_matcher` on every
    request should switch to this function. The behavior is identical the first
    time it is called and after :func:`reset_entity_matcher` clears the cache.
    """
    if force or not _catalog_is_fresh():
        refresh_entity_matcher(db)


# Voice-battery 2026-05-07 (regression fix): Tier 1 intent verbs that appear as
# ≥5-char tokens in queries shouldn't count as "distinctive content" for the
# substring guard. They're function words for intent classification, not entity
# content, and including them would block legitimate matches like "number for
# the tap room" — where "number" is the only ≥5-char query token but doesn't
# substring-match "tap room jiu jitsu". The guard should focus on the entity
# portion of the query, not the intent portion.
_INTENT_VERB_TOKENS: frozenset[str] = frozenset(
    {
        "phone",
        "phones",
        "number",
        "numbers",
        "contact",
        "contacts",
        "address",
        "addresses",
        "location",
        "locations",
        "located",
        "hours",
        "hour",
        "website",
        "websites",
        "rating",
        "ratings",
        "review",
        "reviews",
        "where",
        "called",
        "calling",
    }
)


_SUBSTANTIVE_NEEDLE_TOKEN_MIN_LEN = 5

# Typo substring-guard floors (:func:`_typo_guard_query_token_matches_needle`).
_TYPO_PER_TOKEN_THRESHOLD = 80.0
_TYPO_FIVE_CHAR_NEEDLE_TOKEN_THRESHOLD = 89.0


def _typo_guard_query_token_matches_needle(tok: str, needle: str) -> bool:
    """Return True when ``tok`` clears the substring guard against ``needle``.

    Backlog #44: compare each query token to **substantive** needle tokens (not the full
    phrase), so severe typos like ``mdshrkbrwry`` vs ``mudshark`` score ~85 against
    ``mudshark`` instead of ~72 against the entire canonical.

    Backlog #46: substantive tokens are ≥5 characters so 3–4-char connectors (``and``,
    ``the``, ``for``, ``one``, ``jiu``, …) are not scoring targets — ``partial_ratio``
    against them could reach ~80 for unrelated 6+ char queries.

    Backlog #46 follow-up: for a substantive needle token of **exactly** five characters,
    require ``partial_ratio ≥ 89``. Coincidental matches like ``addrss`` vs ``dress``
    (88.89) stay blocked; longer tokens (e.g. ``mudshark`` at 8 chars) still use the
    80-point floor so ``mdshrkbrwry`` vs ``mudshark`` (85.7) passes.

    When the needle has no ≥5-char tokens, fall back to ``partial_ratio(tok, needle)``
    vs :data:`_TYPO_PER_TOKEN_THRESHOLD` (short canonicals like ``DBR``).
    """
    parts = [p for p in needle.split() if len(p) >= _SUBSTANTIVE_NEEDLE_TOKEN_MIN_LEN]
    if not parts:
        return float(fuzz.partial_ratio(tok, needle)) >= _TYPO_PER_TOKEN_THRESHOLD
    for p in parts:
        pr = float(fuzz.partial_ratio(tok, p))
        thresh = (
            _TYPO_FIVE_CHAR_NEEDLE_TOKEN_THRESHOLD
            if len(p) == _SUBSTANTIVE_NEEDLE_TOKEN_MIN_LEN
            else _TYPO_PER_TOKEN_THRESHOLD
        )
        if pr >= thresh:
            return True
    return False


def _best_score(norm_query: str, needles: frozenset[str]) -> float:
    """Max ``fuzz.token_set_ratio`` across ``needles``, gated by per-needle substring guard.

    Token-set is the safe baseline: it scores by token-set overlap which won't
    score 100 just because one word ("for", "the", "some") is shared. Typo
    tolerance is layered on in :func:`_best_score_padded` against the
    intent-stripped form of the query only, where stopwords have already been
    removed.

    Voice-battery 2026-05-07: when token sets don't intersect, ``token_set_ratio``
    falls back to Levenshtein on the joined sorted strings — which can land
    around 55–65 for two long unrelated strings (empirically: query "what is the
    phone for mudshark brewing" vs needle "double threat barbering co" → 56.25).
    That false-positive scores into the 55–75 near-match band and produces
    wrong-entity gap-template answers. To prevent this, when the query has any
    ≥5-char *content* tokens (intent verbs from :data:`_INTENT_VERB_TOKENS`
    excluded), require at least one of them to substring-match the needle
    (tiered ``partial_ratio`` vs substantive needle tokens — see
    :func:`_typo_guard_query_token_matches_needle`) before letting
    ``token_set_ratio`` count for that needle. When the query has no content
    tokens at all (only short stopwords or only intent verbs), the guard is
    skipped and ``token_set_ratio`` runs unconstrained — that's the right
    behavior because Tier-1-shape queries like "number for the tap room" need
    to match on token-set overlap with the canonical name, not on a substring
    of the intent verb.
    """
    long_query_tokens = [
        t
        for t in norm_query.split()
        if len(t) >= 5 and t.lower() not in _INTENT_VERB_TOKENS
    ]
    best = 0.0
    for needle in needles:
        if long_query_tokens and len(needle) >= 5:
            if not any(
                _typo_guard_query_token_matches_needle(tok, needle)
                for tok in long_query_tokens
            ):
                continue
        best = max(best, float(fuzz.token_set_ratio(norm_query, needle)))
    return best


def _long_tokens(stripped: str) -> str:
    """Return only tokens ≥5 chars from ``stripped``, joined by space.

    Used to filter the query down to its distinctive content words before applying
    :func:`fuzz.partial_token_set_ratio`. Short stopwords ("the", "for", "some")
    are dropped because the partial scorer rewards any single-token substring
    match, and a 3-char token would match nearly every catalog name.
    """
    tokens = [t for t in stripped.split() if len(t) >= 5]
    return " ".join(tokens)


# Voice-battery 2026-05-07: WRatio + partial_token_set_ratio inflate scores when
# the query and needle share only one common token (e.g. "havasu" appears in
# nearly every Lake Havasu provider name) while the *distinctive* token has no
# substring match in the needle. Without a guard, "where can I find havasu lanes"
# matches "Altitude Trampoline Park — Lake Havasu City" via the typo path, since
# WRatio rewards the shared "havasu" + partial overlap. The graded battery
# surfaced six wrong-entity Tier 1 answers from this single failure mode.
# Backlog #46: substantive needle tokens + stricter floor for exactly-5-char tokens.

def _typo_path_passes_guard(long_only: str, needle: str) -> bool:
    """``True`` iff every ≥5-char token in ``long_only`` substring-matches ``needle``.

    Uses :func:`_typo_guard_query_token_matches_needle` per query token. If any
    distinctive query token fails the guard, the typo scorers (WRatio,
    partial_token_set_ratio) do not fire on this needle.

    Backlog #44: per substantive needle token (not full phrase) so severe typos like
    ``"mdshrkbrwry"`` clear via ``"mudshark"``.

    Backlog #46: ≥5-char needle tokens only (connector bypass); exactly-five-char
    tokens need a higher partial_ratio than longer tokens so ``addrss`` vs ``dress``
    does not clear while ``mdshrkbrwry`` vs ``mudshark`` still does.

    Examples (all use the long-tokens-only stripped form of the query):
    - ``"havasu lanes"`` vs ``"havasu lanes"`` → both tokens → PASS.
    - ``"havasu lanes"`` vs ``"altitude trampoline park lake havasu city"``:
      ``"havasu"`` hits 100, ``"lanes"`` max-vs-token hits ~67 → FAIL (was the bug).
    - ``"mudsharks"`` (typo) vs ``"mudshark brewing company"``: ~94 → PASS
      (typo tolerance preserved).
    - ``"mudshark brewing"`` vs ``"double threat barbering co"``:
      ``"mudshark"`` max ~40, ``"brewing"`` max ~77 → FAIL (gap-template guard holds).
    - ``"mdshrkbrwry"`` vs ``"mudshark brewery and public house"``: max ~86 (against
      ``"mudshark"``) → PASS (severe-typo near-match no longer regresses).
    """
    tokens = [t for t in long_only.split() if len(t) >= 5]
    if not tokens:
        return False
    for tok in tokens:
        if not _typo_guard_query_token_matches_needle(tok, needle):
            return False
    return True


# Slice F6: Tier-1-shaped intent prefixes that pad a query with stopwords and drag
# token_set_ratio below threshold. Stripping them isolates the entity portion. Examples:
#   "is mudshark open right now"      → "mudshark" (vs "Mudshark Brewing Company" → 90+)
#   "phone number for the foundry"    → "the foundry"
#   "what are the hours for sloane's" → "sloane's"
# Anchored at start; we keep both forms (stripped + original) and use whichever scores
# higher.
_QUERY_INTENT_PREFIX = re.compile(
    r"^(?:"
    r"is\s+|are\s+|"  # "is X open" / "are X open"
    r"phone\s+(?:number\s+)?for\s+|"
    r"contact\s+(?:number\s+|info\s+)?for\s+|"
    r"contact\s+for\s+|"
    r"call\s+(?:them\s+at\s+|for\s+)?|"
    r"how\s+do\s+i\s+reach\s+|"
    r"reach\s+(?:out\s+to\s+|them\s+at\s+)?|"
    r"address\s+for\s+|"
    r"location\s+of\s+|"
    r"located\s+(?:on\s+\w+\s+\w+\s+)?(?:is\s+|of\s+)?|"
    r"where\s+(?:is\s+|are\s+|'?s\s+)|"
    r"where\s+can\s+i\s+find\s+|"
    r"hours?\s+(?:of\s+operation\s+)?(?:on\s+\w+\s+)?for\s+|"
    r"hour\s+for\s+|"
    r"business\s+hours\s+for\s+|"
    r"what\s+(?:are\s+the\s+)?hours?\s+(?:on\s+\w+\s+)?(?:is\s+|for\s+)?|"
    r"when\s+does\s+|when\s+is\s+|"
    r"what\s+time\s+does\s+|"
    r"opening\s+time\s+for\s+|closing\s+time\s+for\s+|"
    r"website\s+for\s+|site\s+for\s+|url\s+for\s+|link\s+for\s+|landing\s+page\s+for\s+|"
    r"do\s+you\s+have\s+(?:a\s+|the\s+)?website\s+for\s+|"
    r"web\s+address\s+for\s+|"
    r"rating\s+for\s+|star\s+rating\s+for\s+|google\s+rating\s+for\s+|"
    r"how\s+is\s+(?:the\s+)?|how\s+are\s+the\s+reviews\s+for\s+|"
    r"how\s+many\s+stars\s+does\s+|"
    r"number\s+of\s+reviews\s+for\s+|review\s+count\s+for\s+|"
    r"how\s+many\s+reviews\s+does\s+|"
    r"age\s+(?:groups?\s+|range\s+|requirements?\s+)?(?:does\s+)?for\s+|"
    r"what\s+age\s+groups?\s+does\s+|"
    r"how\s+old\s+(?:does\s+)?(?:my\s+kid\s+)?(?:need\s+to\s+be\s+)?for\s+|"
    r"how\s+much\s+(?:does\s+|is\s+)?|pricing\s+for\s+|cost\s+for\s+|fees?\s+for\s+|"
    r"i\s+need\s+(?:the\s+)?(?:phone|website|address|hours)\s+(?:for\s+)?"
    r")",
    re.IGNORECASE,
)

_QUERY_INTENT_SUFFIX = re.compile(
    r"\s+(?:open(?:\s+(?:now|right\s+now|today|tonight))?|"
    r"open\s+at\s+the\s+moment|"
    r"located|please|thanks?|"
    r"have|has|"
    r"on\s+google|"
    r"rated"
    r")\s*\??\s*$",
    re.IGNORECASE,
)


def _strip_intent_padding(norm_query: str) -> str:
    """Return the entity-likely portion of ``norm_query`` after stripping Tier-1 intent
    prefixes and trailing factual qualifiers. Returns the original when nothing matched.
    """
    s = _QUERY_INTENT_PREFIX.sub("", norm_query, count=1)
    s = _QUERY_INTENT_SUFFIX.sub("", s, count=1)
    s = s.strip()
    return s


def _best_score_padded(norm_query: str, needles: frozenset[str]) -> float:
    """Score the query padded, stripped, AND (when safe) with a typo-tolerant scorer.

    Slice F6: queries like "is mudshark open right now" score 50–60 against the bare
    canonical name; stripping the intent padding lifts the score above the 75 threshold
    for the entity that's actually being asked about.

    Slice F (post-fix): typo tolerance via :func:`fuzz.partial_token_set_ratio` is
    applied ONLY on the stripped form AND only when the stripped form is "typo-safe"
    (1–2 tokens, each ≥5 chars). That guard prevents false-positives where a
    common word like "for" or "the" survives stripping and matches anything.
    """
    direct = _best_score(norm_query, needles)
    stripped = _strip_intent_padding(norm_query)
    if not stripped or stripped == norm_query:
        return direct
    boosted = _best_score(stripped, needles)
    typo = 0.0
    long_only = _long_tokens(stripped)
    if long_only:
        for needle in needles:
            # Skip very short canonicals — partial_token_set_ratio + WRatio inflate
            # scores when the target is 2–4 chars (e.g. "DBR", "76", "IHOP") because
            # both algorithms fall back to substring scanning that finds spurious
            # matches in any longer query string.
            if len(needle) < 5:
                continue
            # Voice-battery 2026-05-07: per-token substring guard. Without this,
            # a single shared common token ("havasu") + WRatio's permissive
            # composite scoring lets non-matching needles cross the 75 threshold.
            if not _typo_path_passes_guard(long_only, needle):
                continue
            # Slice F: max of partial_token_set_ratio + WRatio for typo tolerance.
            # WRatio combines token_sort + partial_ratio + others with internal
            # weighting, which crucially distinguishes "mudsharks brewry" → "mudshark
            # brewery..." (84) from the wrong-target "mudshark pizza..." (50). The
            # partial scorer catches the symmetric case where target is shorter.
            wr = float(fuzz.WRatio(long_only, needle))
            ptsr = float(fuzz.partial_token_set_ratio(long_only, needle))
            typo = max(typo, wr, ptsr)
    return max(direct, boosted, typo)


def _provider_id_for_name(db: Session, provider_name: str) -> str:
    """Resolve ``Provider.id`` when present; else fall back to name (same as ``record_entity``)."""
    name = (provider_name or "").strip()
    if not name:
        return ""
    try:
        row = db.scalars(select(Provider).where(Provider.provider_name == name).limit(1)).first()
        if row is not None:
            return str(row.id)
    except Exception:
        pass
    return name


# Backlog #50: minimum-length floor at matcher entry points.
#
# Smoke catalog Class C2 (2026-05-08) flagged that single-char queries like
# ``"a"`` fuzzy-match short canonical prefixes (``"A & A Electronics
# Assembly"``, etc.) and produce wrong-entity Tier 1 answers. Pre-existing
# behavior — not a regression — but a hard floor at the matcher boundary is
# the cleanest fix.
#
# Centralized in :func:`_normalize_for_match` rather than duplicated at each
# entry. All four direct entry points (``extract_catalog_entities_from_text``,
# ``match_entity_with_ambiguity``, ``find_near_match``, ``match_entity_with_rows``)
# already call ``normalize(query)`` followed by ``if not norm: return …``;
# swapping ``normalize`` for ``_normalize_for_match`` is a one-line change per
# site and gives us a single source of truth for the floor + the
# normalize-then-floor ordering. ``match_entity`` and
# ``query_has_ambiguous_entities`` delegate to ``match_entity_with_ambiguity``,
# so they inherit the floor for free.
_MIN_QUERY_LENGTH = 3

# Phase 7.5.5 — structurally-fake token gate.
#
# Junk queries like ``"When is the zzznonexistentevent999abc?"`` produce false-
# positive did-you-mean replies because rapidfuzz's substring scorers find
# spurious matches between ``zzznonexistentevent999abc`` and short catalog
# tokens (e.g. ``"steven"`` — the ``"even"`` substring scores 83.3 on
# ``partial_ratio`` and clears the 80-point typo guard floor, pulling the row
# into the 55–75 near-match band against names like "Biehn Steven A").
#
# The fix mirrors the structural-heuristic pattern already shipped in
# :func:`app.chat.entity_intent._looks_structurally_fake` (Phase 7.5.3 F1) but
# scoped per-token, not per-query, because the matcher's input has typically
# already been stripped of intent verbs by ``_strip_intent_padding`` and may
# only carry one or two surviving tokens. A query containing **any** token
# that looks structurally fabricated is rejected at the matcher boundary.
#
# Load-bearing negative regression: legitimate severe typos like
# ``"mdshrkbrwry"`` (vowels-dropped form of "mudshark brewery") must still
# clear the gate — they are pure-consonant but contain no digits and are not
# ≥15 chars. The Backlog #44 escape hatch for severe typos still works.
_STRUCTURAL_FAKE_MIN_LONG_TOKEN_LEN = 15
_STRUCTURAL_FAKE_MIN_VOWEL_DENSITY = 0.30
_DIGIT_RUN_RE = re.compile(r"\d{3,}")
_HAS_LETTER_RE = re.compile(r"[a-z]", re.I)
_HAS_DIGIT_RE = re.compile(r"\d")
_LONG_CONSONANT_RUN_RE = re.compile(r"[bcdfghjklmnpqrstvwxyz]{6,}", re.I)


def _token_vowel_density(tok: str) -> float:
    letters = [c for c in tok.lower() if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if c in "aeiouy") / len(letters)


def _token_looks_structurally_fake(tok: str) -> bool:
    """True when ``tok`` is shaped like a fabricated entity name (Phase 7.5.5).

    Three independent triggers — any one fires:

    1. **Embedded digit run** — token has 3+ consecutive digits AND letters
       (e.g. ``"event999abc"``, ``"joe9999tavern"``, ``"business4042"``).
       Pure numeric tokens like ``"2024"`` are not flagged here — they fail
       the letter check and may be legitimate (e.g. event dates).
    2. **Long alphanumeric with low vowels** — token is ≥15 chars AND vowel
       density is <30% (catches ``"zzznonexistentevent999abc"`` shape).
    3. **Consonant-run + digits** — token has a 6+ consecutive-consonant run
       AND contains at least one digit (catches ``"lhcbba999"`` shape).

    Pure-consonant typos (``"mdshrkbrwry"``, 11 chars, 0 digits) are NOT
    flagged — they fall through every trigger and remain matchable via the
    Backlog #44 severe-typo escape hatch.
    """
    if not tok:
        return False
    has_letter = bool(_HAS_LETTER_RE.search(tok))
    has_digit = bool(_HAS_DIGIT_RE.search(tok))
    if has_letter and _DIGIT_RUN_RE.search(tok):
        return True
    if len(tok) >= _STRUCTURAL_FAKE_MIN_LONG_TOKEN_LEN:
        if _token_vowel_density(tok) < _STRUCTURAL_FAKE_MIN_VOWEL_DENSITY:
            return True
    if has_digit and _LONG_CONSONANT_RUN_RE.search(tok):
        return True
    return False


def _query_has_structurally_fake_token(norm_query: str) -> bool:
    """True when the normalized query contains a structurally fake token.

    A single fake-shaped token taints the whole query — the user wrote a junk
    string interleaved with real words (e.g. ``"when is the
    zzznonexistentevent999abc"`` has ``"zzznonexistentevent999abc"`` as the
    only ≥5-char content token, but even with stopwords stripped the user did
    not name a real entity). Returning True at the matcher boundary lets the
    caller surface the generic gap template instead of a spurious did-you-mean.
    """
    for tok in norm_query.split():
        if _token_looks_structurally_fake(tok):
            return True
    return False


def _normalize_for_match(query: str) -> str:
    """Normalize and apply the ≥3-char minimum-length floor (Backlog #50).

    Returns the normalized query when it carries at least
    :data:`_MIN_QUERY_LENGTH` chars of content. Returns ``""`` otherwise —
    callers already treat empty-string normalize output as the "no match"
    signal (``if not norm: return …``), so the floor is transparent to them.

    Floor is applied AFTER ``normalize()`` so whitespace-padded short queries
    like ``"  a  "`` (which normalize to a 1-char string) are also blocked.

    Phase 7.5.5: also rejects queries containing a structurally fake token
    (digit-run inside letters, long low-vowel alphanumeric, or consonant-run
    + digits). See :func:`_token_looks_structurally_fake`.
    """
    norm = normalize(query)
    if len(norm) < _MIN_QUERY_LENGTH:
        return ""
    if _query_has_structurally_fake_token(norm):
        return ""
    return norm


def extract_catalog_entities_from_text(text: str, db: Session) -> list[EntityMatch]:
    """Return all catalog **providers** mentioned in *text* with fuzzy score strictly above 75.

    Uses the same in-memory index as :func:`match_entity`. Each hit is deduplicated by canonical
    name (one entry per provider). ``type`` is always ``"provider"`` for Phase 6.4.1.
    """
    global _rows
    if _rows is None:
        refresh_entity_matcher(db)
    assert _rows is not None

    norm = _normalize_for_match(text)
    if not norm:
        return []

    best_by_canon: dict[str, float] = {}
    for row in _rows:
        if _category_guard_skips_row(norm, row):
            continue
        s = _best_score_padded(norm, row.needles)
        if s > 75.0:
            prev = best_by_canon.get(row.canonical)
            if prev is None or s > prev:
                best_by_canon[row.canonical] = s

    out: list[EntityMatch] = []
    for name in sorted(best_by_canon.keys()):
        pid = _provider_id_for_name(db, name)
        out.append(EntityMatch(name=name, type="provider", id=pid))
    return out


# Slice F §3.2: ambiguity detection. When the top score and runner-up are within
# this margin AND both above 75, the matcher returns None — the user's query maps to
# multiple candidates equally well (e.g. "phone for the diner" with three diners),
# and Tier 3 should disambiguate using the context block instead of Tier 1 picking
# arbitrarily.
_AMBIGUITY_MARGIN = 8.0


def match_entity_with_ambiguity(
    query: str, db: Session
) -> tuple[tuple[str, float] | None, bool]:
    """Return ``(top_match_or_none, is_ambiguous)``.

    Slice F §3.2 (post-revert): the matcher always returns the top match if it clears
    the 75 threshold — even when a runner-up is near-tied. Picking arbitrarily on tie
    (alphabetical order) is the lesser-evil compared to dropping the match entirely
    and routing to a (currently-broken-on-prod) Tier 3 disambiguation reply. The
    ``is_ambiguous`` flag is still computed and returned so a future deterministic
    disambiguation path can use it without another schema change.
    """
    global _rows
    if _rows is None:
        refresh_entity_matcher(db)
    assert _rows is not None

    norm = _normalize_for_match(query)
    if not norm:
        return None, False

    best_canon: str | None = None
    best_score = -1.0
    second_score = -1.0
    for row in _rows:
        if _category_guard_skips_row(norm, row):
            continue
        s = _best_score_padded(norm, row.needles)
        if s > best_score:
            second_score = best_score
            best_score = s
            best_canon = row.canonical
        elif s == best_score and best_canon is not None and row.canonical < best_canon:
            second_score = s
            best_canon = row.canonical
        elif s > second_score:
            second_score = s

    if best_canon is None or best_score <= 75.0:
        return None, False

    is_ambiguous = (
        second_score > 75.0 and (best_score - second_score) < _AMBIGUITY_MARGIN
    )
    return (best_canon, best_score), is_ambiguous


def match_entity(query: str, db: Session) -> tuple[str, float] | None:
    """Return ``(provider_name, score)`` if the best fuzzy match is strictly above 75.

    The index covers distinct ``Program.provider_name`` values (denormalized string,
    historical) plus active non-draft ``Provider`` rows (the unified provider table —
    both event-host providers and Google Places businesses). Call
    :func:`refresh_entity_matcher` after bulk program imports or provider loads.

    Slice F §3.2 (post-revert): on a tie among multiple strong matches, the function
    returns the alphabetically-first canonical (deterministic). To detect ambiguity,
    call :func:`match_entity_with_ambiguity` which returns the same match plus an
    ``is_ambiguous`` flag.
    """
    hit, _ambiguous = match_entity_with_ambiguity(query, db)
    return hit


# Slice F: queries scoring in this band against the catalog look like plausible
# typos but don't clear the strict 75 threshold for an exact-match Tier 1 reply.
# The router uses :func:`find_near_match` to offer a "Did you mean X?" disambiguation
# before falling to the standard gap template.
_NEAR_MATCH_LOW = 55.0
_NEAR_MATCH_HIGH = 75.0


def find_near_match(query: str, db: Session) -> tuple[str, float] | None:
    """Return ``(canonical, score)`` when the top fuzzy score is in the near-match
    band (55–75 inclusive on the low side, exclusive on the high side).

    Returns ``None`` when the top score is above 75 (a real match — caller should
    use :func:`match_entity` instead) or below 55 (no plausible candidate — caller
    should show the standard gap copy).
    """
    global _rows
    if _rows is None:
        refresh_entity_matcher(db)
    assert _rows is not None

    norm = _normalize_for_match(query)
    if not norm:
        return None

    best_canon: str | None = None
    best_score = -1.0
    for row in _rows:
        if _category_guard_skips_row(norm, row):
            continue
        s = _best_score_padded(norm, row.needles)
        if s > best_score:
            best_score = s
            best_canon = row.canonical
        elif s == best_score and best_canon is not None and row.canonical < best_canon:
            best_canon = row.canonical

    if best_canon is None:
        return None
    if not (_NEAR_MATCH_LOW <= best_score < _NEAR_MATCH_HIGH):
        return None
    return (best_canon, best_score)


def query_has_ambiguous_entities(query: str, db: Session) -> bool:
    """``True`` when the entity matcher's top match has a near-tied runner-up.

    Currently advisory only — no caller acts on the flag (the gap-response path that
    used to skip on ambiguity was reverted because it over-fired in production with
    2,266 providers and dropped users into the broken Tier 3 LLM path).
    """
    _hit, ambiguous = match_entity_with_ambiguity(query, db)
    return ambiguous


def match_entity_with_rows(query: str, canonical_names: Sequence[str]) -> tuple[str, float] | None:
    """Match *query* against an explicit list of canonical provider names (no DB)."""
    norm = _normalize_for_match(query)
    if not norm:
        return None
    best_canon: str | None = None
    best_score = -1.0
    for c in canonical_names:
        c = c.strip()
        if not c:
            continue
        needles = _needles_for_canonical(c)
        erow = _EntityRow(c, needles, _synthetic_category_blob(c, needles))
        if _category_guard_skips_row(norm, erow):
            continue
        s = _best_score_padded(norm, needles)
        if s > best_score:
            best_score = s
            best_canon = c
        elif s == best_score and best_canon is not None and c < best_canon:
            best_canon = c
    if best_canon is None or best_score <= 75.0:
        return None
    return (best_canon, best_score)
