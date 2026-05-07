"""Fuzzy match user queries to a canonical ``Program.provider_name``."""

from __future__ import annotations

import re
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


@dataclass(frozen=True)
class EntityMatch:
    """One catalog provider mentioned in free text (Phase 6.4.1)."""

    name: str
    type: str
    id: str


_rows: list[_EntityRow] | None = None


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
    global _rows
    program_names = db.scalars(select(Program.provider_name).distinct()).all()
    provider_names = db.scalars(
        select(Provider.provider_name).where(
            Provider.is_active.is_(True), Provider.draft.is_(False)
        )
    ).all()
    canon = sorted(
        {(n or "").strip() for n in (*program_names, *provider_names) if (n or "").strip()}
    )
    _rows = [_EntityRow(c, _needles_for_canonical(c)) for c in canon]


def reset_entity_matcher() -> None:
    """Clear the cache (mainly for tests)."""
    global _rows
    _rows = None


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
    ≥5-char tokens, require at least one of them to substring-match the needle
    (``partial_ratio ≥ 80``) before letting ``token_set_ratio`` count for that
    needle. Short queries with no long tokens are unaffected.
    """
    long_query_tokens = [t for t in norm_query.split() if len(t) >= 5]
    best = 0.0
    for needle in needles:
        if long_query_tokens and len(needle) >= 5:
            if not any(
                float(fuzz.partial_ratio(tok, needle)) >= _TYPO_PER_TOKEN_THRESHOLD
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
_TYPO_PER_TOKEN_THRESHOLD = 80.0


def _typo_path_passes_guard(long_only: str, needle: str) -> bool:
    """``True`` iff every ≥5-char token in ``long_only`` substring-matches ``needle``.

    Uses :func:`fuzz.partial_ratio` (Levenshtein-style best-window ratio) per
    query token. If any distinctive query token has no substring-like match in
    the needle, the typo scorers (WRatio, partial_token_set_ratio) are not
    allowed to fire on this needle — preventing the wrong-entity false positives
    surfaced by the voice battery.

    Examples (all use the long-tokens-only stripped form of the query):
    - ``"havasu lanes"`` vs ``"havasu lanes"`` → both tokens → PASS.
    - ``"havasu lanes"`` vs ``"altitude trampoline park lake havasu city"``:
      ``"havasu"`` hits 100, ``"lanes"`` hits ~25 → FAIL (was the bug).
    - ``"mudsharks"`` (typo) vs ``"mudshark brewing company"``: ~89 → PASS
      (typo tolerance preserved).
    - ``"mudshark brewing"`` vs ``"double threat barbering co"``:
      ``"mudshark"`` hits ~30, ``"brewing"`` hits ~57 (b/r/i/n shared with
      ``barbering``) → FAIL (was the gap-template near-match bug).
    """
    tokens = [t for t in long_only.split() if len(t) >= 5]
    if not tokens:
        return False
    for tok in tokens:
        if float(fuzz.partial_ratio(tok, needle)) < _TYPO_PER_TOKEN_THRESHOLD:
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


def extract_catalog_entities_from_text(text: str, db: Session) -> list[EntityMatch]:
    """Return all catalog **providers** mentioned in *text* with fuzzy score strictly above 75.

    Uses the same in-memory index as :func:`match_entity`. Each hit is deduplicated by canonical
    name (one entry per provider). ``type`` is always ``"provider"`` for Phase 6.4.1.
    """
    global _rows
    if _rows is None:
        refresh_entity_matcher(db)
    assert _rows is not None

    norm = normalize(text)
    if not norm:
        return []

    best_by_canon: dict[str, float] = {}
    for row in _rows:
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

    norm = normalize(query)
    if not norm:
        return None, False

    best_canon: str | None = None
    best_score = -1.0
    second_score = -1.0
    for row in _rows:
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

    norm = normalize(query)
    if not norm:
        return None

    best_canon: str | None = None
    best_score = -1.0
    for row in _rows:
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
    norm = normalize(query)
    if not norm:
        return None
    best_canon: str | None = None
    best_score = -1.0
    for c in canonical_names:
        c = c.strip()
        if not c:
            continue
        needles = _needles_for_canonical(c)
        s = _best_score_padded(norm, needles)
        if s > best_score:
            best_score = s
            best_canon = c
        elif s == best_score and best_canon is not None and c < best_canon:
            best_canon = c
    if best_canon is None or best_score <= 75.0:
        return None
    return (best_canon, best_score)
