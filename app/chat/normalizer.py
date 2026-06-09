"""Normalize user queries before intent classification and entity matching."""

from __future__ import annotations

import re
import string
from functools import lru_cache

from rapidfuzz import fuzz, process

# Apply after lowercasing. Apostrophe forms first, then apostrophe-less variants.
_CONTRACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bwhat's\b"), "what is"),
    (re.compile(r"\bwhen's\b"), "when is"),
    (re.compile(r"\bwhere's\b"), "where is"),
    (re.compile(r"\bwho's\b"), "who is"),
    (re.compile(r"\bhow's\b"), "how is"),
    (re.compile(r"\bit's\b"), "it is"),
    (re.compile(r"\bthat's\b"), "that is"),
    (re.compile(r"\bthere's\b"), "there is"),
    (re.compile(r"\bi'm\b"), "i am"),
    (re.compile(r"\bwhats\b"), "what is"),
    (re.compile(r"\bwhens\b"), "when is"),
    (re.compile(r"\bwheres\b"), "where is"),
    (re.compile(r"\bwhos\b"), "who is"),
)

_EDGE_CHARS = frozenset(string.punctuation + string.whitespace)


def _strip_edge_punct_ws(text: str) -> str:
    if not text:
        return text
    lo, hi = 0, len(text)
    while lo < hi and text[lo] in _EDGE_CHARS:
        lo += 1
    while hi > lo and text[hi - 1] in _EDGE_CHARS:
        hi -= 1
    return text[lo:hi]


# ---------------------------------------------------------------------------
# Domain-aware spell correction (2026-06-09). One shared layer so misspelling
# tolerance applies at EVERY chat level: ``normalize`` is the single funnel that
# the intent classifier, entity matcher, Tier-1 handler, intent layer, and
# unified router all run through, so correcting here lifts every consumer at
# once. ``leaf_query`` keeps its own normalizer (it predates this funnel) and
# calls :func:`spell_correct` explicitly so /chat navigational routing benefits
# too.
#
# The corrected string is what routing/classification sees; the ORIGINAL raw
# query is preserved separately by callers (IntentResult.raw_query, and the
# Tier-3 LLM is handed the raw ``query``) so the model still sees what the user
# typed.
#
# Conservative by construction so we never "correct" a distinctive proper noun
# (a real business name) into a category word:
#   * only pure-alpha tokens of length >= _SPELL_MIN_LEN are candidates,
#   * a token already in the vocab is left alone (it is canonical),
#   * a high score cutoff (_SPELL_CUTOFF) plus a length-delta guard,
#   * an explicit PROTECTED set of real English words that collide with a
#     category term but mean something else (hostels≠hotels), and
#   * an ALIAS map for slang/phonetic forms that edit-distance can't reach
#     (dawg→dog).
# ---------------------------------------------------------------------------

_SPELL_CUTOFF = 90.0  # fuzz.ratio score; tuned so all adversarial cases pass
_SPELL_MIN_LEN = 5  # skip short tokens (cars/jets/bars/vets never auto-correct)
_SPELL_MIN_CANDIDATE_LEN = 6  # never auto-correct TO a 5-char word: too many real
# 6-char words sit one edit from a 5-char category word (saloon/salon,
# sparks/parks, snails/nails). Every genuine trade target is >= 7 chars, so this
# costs nothing and kills that whole false-positive band. Short-target trades
# (salon, gym) are handled by exact aliases instead.
_SPELL_MAX_LEN_DELTA = 2  # candidate length must be within this of the token

# Common words that look like a category term but are semantically distinct.
# Never auto-corrected. "saloon" in Lake Havasu reads as a bar/tavern, NOT a
# misspelling of "salon" (carried over from the prior tier2 typo map). The
# others are real words that survive the length guards but mean something else.
_SPELL_PROTECTED: frozenset[str] = frozenset(
    {"hostel", "hostels", "saloon", "sparks", "snails", "moves"}
)

# Exact-match corrections edit-distance shouldn't or can't make on its own:
# slang/phonetic forms (dawg→dog) and the hand-curated service-trade
# misspellings consolidated here from app.chat.tier2_business_shortcut so the
# whole product shares ONE correction layer. Exact lookup → zero false-positive
# risk, which is why short-target trades (gym, salon) live here rather than in
# the fuzzy path.
_SPELL_ALIASES: dict[str, str] = {
    # slang / phonetic
    "dawg": "dog",
    "dawgs": "dogs",
    # plumbing
    "plumer": "plumber",
    "plummer": "plumber",
    "plumming": "plumbing",
    # barbering
    "barbar": "barber",
    "barbor": "barber",
    "barbur": "barber",
    # electrical
    "elektrician": "electrician",
    "electrision": "electrician",
    "electricion": "electrician",
    "electrican": "electrician",
    # mechanic / auto
    "mecanic": "mechanic",
    "mechanik": "mechanic",
    "mechinic": "mechanic",
    # veterinary
    "vetrinarian": "veterinarian",
    "veternarian": "veterinarian",
    "vetrinary": "veterinary",
    "veternary": "veterinary",
    # food / drink
    "resturant": "restaurant",
    "restaraunt": "restaurant",
    "restuarant": "restaurant",
    "coffe": "coffee",
    "cofee": "coffee",
    "coffey": "coffee",
    # pharmacy / health
    "pharamcy": "pharmacy",
    "pharmasy": "pharmacy",
    "pharmcy": "pharmacy",
    # trades / misc
    "carpentar": "carpenter",
    "carpentor": "carpenter",
    "landscapper": "landscaper",
    "gymn": "gym",
    "salaon": "salon",
}

# Filler/function words dropped from the vocab so a typo never "corrects" to one.
_SPELL_STOPWORDS: frozenset[str] = frozenset(
    {
        "to", "me", "a", "an", "the", "in", "of", "and", "for", "is", "it", "at",
        "on", "near", "you", "my", "good", "best", "top", "find", "show", "some",
        "any", "all", "every", "open", "now", "here", "there",
    }
)

_TOKEN_ALPHA_RE = re.compile(r"^[a-z]+$")

# Inflectional suffixes. When a token and its candidate differ ONLY by one of
# these trailing endings (one is the other plus the suffix), they are the same
# real word in a different form, not a typo — so we leave the token alone. This
# is what separates "place"→"places" / "changed"→"change" (skip) from
# "dentis"→"dentist" (a "+t" remainder, not a real suffix → correct). Without it
# fuzz.ratio scores both kinds identically and a cutoff cannot tell them apart.
_MORPH_SUFFIXES: frozenset[str] = frozenset(
    {"s", "es", "d", "ed", "ing", "er", "ers", "ly", "y", "ies", "ment", "ness", "al", "ion"}
)


def _is_morphological_variant(a: str, b: str) -> bool:
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if short == long or not long.startswith(short):
        return False
    return long[len(short) :] in _MORPH_SUFFIXES


@lru_cache(maxsize=1)
def _spell_vocab() -> frozenset[str]:
    """Build the canonical-term vocabulary (single word tokens), built once.

    Sources: the ``leaf_query`` colloquial→leaf map keys, the Tier-2 category
    synonym groups, and the intent-layer controlled dictionaries. Imported
    lazily to avoid an import cycle (this module is imported very early by the
    classifier / entity matcher); by first-call time every module is loaded.
    """
    from app.categories.leaf_query import _QUERY_TO_LEAF
    from app.chat.intents.dicts import CUISINE_DICT, SERVICE_DICT, SYMPTOM_MAP
    from app.chat.tier2_synonyms import _CATEGORY_SYNONYM_GROUPS

    vocab: set[str] = set()

    def _add_phrase(phrase: str) -> None:
        for word in re.split(r"[\s/&-]+", phrase.strip().lower()):
            if len(word) >= 3 and word not in _SPELL_STOPWORDS and _TOKEN_ALPHA_RE.match(word):
                vocab.add(word)

    for key in _QUERY_TO_LEAF:
        _add_phrase(key)
    for group in _CATEGORY_SYNONYM_GROUPS:
        for term in group:
            _add_phrase(term)
    for key in SERVICE_DICT:
        _add_phrase(key)
    for key in CUISINE_DICT:
        _add_phrase(key)
    for key in SYMPTOM_MAP:
        _add_phrase(key)
    return frozenset(vocab)


def _correct_token(token: str) -> str:
    """Return the canonical vocab term for ``token`` or ``token`` unchanged."""
    if token in _SPELL_ALIASES:
        return _SPELL_ALIASES[token]
    if not _TOKEN_ALPHA_RE.match(token):
        return token  # numbers, hyphenated/apostrophe forms → likely proper nouns
    vocab = _spell_vocab()
    if token in vocab or token in _SPELL_PROTECTED or len(token) < _SPELL_MIN_LEN:
        return token
    match = process.extractOne(token, vocab, scorer=fuzz.ratio, score_cutoff=_SPELL_CUTOFF)
    if match is None:
        return token
    candidate = match[0]
    if len(candidate) < _SPELL_MIN_CANDIDATE_LEN:
        return token
    if abs(len(candidate) - len(token)) > _SPELL_MAX_LEN_DELTA:
        return token
    if _is_morphological_variant(token, candidate):
        return token  # "place"→"places", "changed"→"change": same word, not a typo
    return candidate


def spell_correct(text: str) -> str:
    """Token-wise domain spell correction over an already-lowercased string.

    Replaces each near-miss query token with its canonical category/trade term
    while leaving in-vocab words, short words, protected real words, and
    distinctive proper nouns untouched. Idempotent on already-correct input.
    """
    if not text:
        return text
    tokens = text.split()
    if not tokens:
        return text
    corrected = [_correct_token(tok) for tok in tokens]
    return " ".join(corrected) if corrected != tokens else text


def normalize(query: str) -> str:
    """Return a normalized query string for routing.

    - Lowercase
    - Strip leading/trailing whitespace and punctuation
    - Expand common informal contractions (``whens`` → ``when is``, etc.)
    - Collapse internal runs of whitespace to a single space
    - Preserve internal hyphens and apostrophes (e.g. ``o'clock``, ``co-op``)
    - Domain-aware spell correction (``plummbers`` → ``plumbers``) so every
      chat level inherits misspelling tolerance from this one shared layer
    """
    if not query:
        return ""
    s = query.strip().lower()
    for pattern, repl in _CONTRACTIONS:
        s = pattern.sub(repl, s)
    s = _strip_edge_punct_ws(s)
    s = re.sub(r"\s+", " ", s).strip()
    s = spell_correct(s)
    return s


# ---------------------------------------------------------------------------
# Cache-key canonicalization (2026-06-06). The Tier-2 parser/formatter caches
# and the Tier-3 exact-key cache were keyed on the raw normalized string, so a
# courtesy lead-in or a redundant locality suffix ("... in lake havasu",
# "... near me" — this is a single-town product) made every phrasing a cache
# miss that re-paid the LLM. Strip ONLY tokens that carry no intent in this
# product; anything ambiguous stays in the key (a wrong canonical key serves a
# wrong cached answer, which is worse than a miss).
# ---------------------------------------------------------------------------

_CACHE_LEADIN_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(?:hey|hi|ok|okay)[\s,]+hava[\s,!.]+"),
    re.compile(r"^hava[\s,!.]+"),
    re.compile(r"^please[\s,]+"),
    re.compile(r"^(?:can|could|will|would)\s+you\s+(?:please\s+)?tell\s+me[\s,]+"),
)

_CACHE_SUFFIX_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"[\s,]+in\s+lake\s+havasu(?:\s+city)?$"),
    re.compile(r"[\s,]+in\s+havasu$"),
    re.compile(r"[\s,]+(?:in|around)\s+town$"),
    re.compile(r"[\s,]+around\s+here$"),
    re.compile(r"[\s,]+near\s+me$"),
    re.compile(r"[\s,]+nearby$"),
    re.compile(r"[\s,]+please$"),
    re.compile(r"[\s,]+thanks$"),
    re.compile(r"[\s,]+thank\s+you$"),
)


def canonicalize_for_cache(normalized_query: str) -> str:
    """Fold no-intent lead-ins/suffixes out of a cache key. Lookup-key only —
    never feed this to the LLM or to entity matching (the locality suffix IS
    meaningful to entity queries like "the hangar in lake havasu")."""
    s = (normalized_query or "").strip().lower()
    if not s:
        return s
    changed = True
    while changed:
        changed = False
        for rx in _CACHE_LEADIN_RES:
            new = rx.sub("", s).strip()
            if new and new != s:
                s, changed = new, True
        for rx in _CACHE_SUFFIX_RES:
            new = rx.sub("", s).strip()
            if new and new != s:
                s, changed = new, True
    return re.sub(r"\s+", " ", s)
