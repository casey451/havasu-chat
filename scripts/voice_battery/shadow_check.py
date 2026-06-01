"""Shadow voice battery — pure-Python routing simulator with inline regex patterns.

Why this exists: the bash sandbox snapshot lags behind the actual on-disk state of the
chat module, so importing `app.chat.unified_router` from the sandbox fails. This script
inlines the routing-relevant regexes (mirrored from `app/chat/intent_classifier.py`,
`app/chat/tier1_templates.py`, `app/chat/tier2_business_shortcut.py`, `app/core/intent.py`,
and the gap-response logic in `app/chat/unified_router.py`) so the simulation can run
locally and produce a routing-accurate report without app imports.

Run via:
    python -m scripts.voice_battery.shadow_check

Output: tests/voice_battery/reports/shadow_check.md

The simulation predicts:
- mode (ask | contribute | correct | chat)
- sub_intent (Tier 1 sub_intent name | OPEN_ENDED | LIST_BY_CATEGORY | GREETING | …)
- routing tier (1 | 2 | 3 | gap_template | chat | placeholder)
- predicted Tier 1 response shape (template + slot keys it would fill)
- Tier 2 listing extracted category
- entity match probability (substring against the loaded LHC business catalog)

It does NOT call the LLM, hit the DB, or depend on any app module. The 200 questions
in `tests/voice_battery/questions.yaml` are scored against this prediction; the report
groups by intent_shape and flags routing mismatches against expected_tier.
"""

from __future__ import annotations

import json
import re
import string
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = REPO_ROOT / "tests" / "voice_battery" / "questions.yaml"
PROVIDERS_JSONL = REPO_ROOT / "scripts" / "output" / "places_pull" / "enrichment_enriched.jsonl"
REPORT_DIR = REPO_ROOT / "tests" / "voice_battery" / "reports"
REPORT_MD = REPORT_DIR / "shadow_check.md"

# =====================================================================
# Inline regex patterns — mirror of post-Slice-F state
# =====================================================================

# normalize() — same as app/chat/normalizer.py
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


def normalize(query: str) -> str:
    if not query:
        return ""
    s = query.strip().lower()
    for pattern, repl in _CONTRACTIONS:
        s = pattern.sub(repl, s)
    lo, hi = 0, len(s)
    while lo < hi and s[lo] in _EDGE_CHARS:
        lo += 1
    while hi > lo and s[hi - 1] in _EDGE_CHARS:
        hi -= 1
    s = s[lo:hi]
    s = re.sub(r"\s+", " ", s).strip()
    return s


# INTENT_PATTERNS — mirror of tier1_templates.py post-Slice-F4
INTENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "REVIEW_COUNT_LOOKUP",
        re.compile(
            r"\b("
            r"how many reviews|number of reviews|review count|reviews count|"
            r"how many ratings|number of ratings|how many people reviewed"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "RATING_LOOKUP",
        re.compile(
            r"\b("
            r"rating|ratings|star rating|how many stars|stars on google|"
            r"google rating|how is .{0,30}rated|are they rated|rated highly|"
            r"any good reviews|how are the reviews|are the reviews good|"
            r"is .{0,40}any good|are they any good"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    ("WEBSITE_LOOKUP", re.compile(r"\b(website|site|url|web address|link|landing page)\b")),
    (
        "PHONE_LOOKUP",
        re.compile(
            r"\b(phone number|phone|contact number|contact info|contact|"
            r"call them|call for|reach (?:them|out)|reach|number)\b"
        ),
    ),
    (
        "AGE_LOOKUP",
        re.compile(r"\b(age groups?|age range|age requirements?|ages?|how old|youngest age)\b"),
    ),
    ("COST_LOOKUP", re.compile(r"\b(how much|cost|costs|pricing|price|fees?)\b")),
    (
        "TIME_LOOKUP",
        re.compile(r"\b(what time|start time|opening time|closing time|open time|close time)\b"),
    ),
    (
        "HOURS_LOOKUP",
        re.compile(
            r"\b("
            r"hours?|open now|open right now|open late|open early|opens late|opens early|"
            r"close at what time|what time\b.+\b(close|closes|closing)\b"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    ("LOCATION_LOOKUP", re.compile(r"\b(where|located|location|address)\b")),
    ("DATE_LOOKUP", re.compile(r"\b(when|dates?)\b")),
]

# Mode-level heuristics — mirror of intent_classifier.py
_CORRECT_MARKERS = (
    re.compile(r"\b(actually it is|actually it's|actually it is)\b"),
    re.compile(r"\b(that is wrong|that's wrong|that is incorrect|that's incorrect)\b"),
    re.compile(r"\b(is not at|isn't at|not at that address)\b"),
    re.compile(r"\b(moved to|changed to|relocated to)\b"),
    re.compile(r"\b(now it is|now it's)\b"),
    re.compile(r"\bused to be\b"),
    re.compile(r"\b(you have the wrong|wrong phone|wrong address|wrong time)\b"),
    re.compile(r"\bthe (phone|address|time|date|location|hours|website)\b.+\bis actually\b"),
)

_CONTRIBUTE_MARKERS = (
    re.compile(r"^\s*(there is a|there is an)\b"),
    re.compile(
        r"\bthere is a\b.+\b(happening|scheduled|this weekend|on saturday|on sunday|on friday)\b"
    ),
    re.compile(r"\b(just opened|grand opening)\b"),
    re.compile(r"\bnew event\b"),
    re.compile(r"\b(i want to add|want to add|need to add|going to add)\b"),
    re.compile(r"\bput in a\b"),
    re.compile(r"\b(post an event|submit an event|submit this event)\b"),
    re.compile(r"\bi have a .+ to add\b"),
    re.compile(r"\b(adding a|adding an|adding my|adding the)\b"),
    re.compile(r"^\s*new business\b"),
    re.compile(r"^\s*new program\b"),
    re.compile(r"\badding weekly\b"),
    re.compile(r"^\s*adding karate\b"),
    re.compile(r"\bnew youth program\b"),
    re.compile(r"\bwe are having\b"),
    re.compile(r"\b(i am hosting|hosting a)\b"),
)

_GREETING_ONLY = re.compile(
    r"^\s*(hi|hey|hello|howdy|good morning|good afternoon|good evening|what is up|sup)\b"
    r"([\s,!.]*)(there|you|everyone|team)?[\s,!.]*$",
    re.IGNORECASE,
)

_REAL_ESTATE_CHAT = re.compile(
    r"\b(buy a house|buying a house|buy a home|sell my house|sell our house|real estate|realtor|mortgage|"
    r"home prices|list my home)\b",
    re.IGNORECASE,
)

_SMALL_TALK = re.compile(
    r"^\s*(thanks|thank you|thx|ty|appreciate it|much appreciated|how are you|how is it going|"
    r"you are the best|you rock|bye|goodbye|good night|goodnight)\b[\s,!.]*$",
    re.IGNORECASE,
)

_NEXT_OCCURRENCE = re.compile(
    r"\b(when is the next|when's the next|when is the upcoming|next occurrence of)\b|"
    r"\bnext\s+(bmx|race|class|session|game|event|meet|meeting|show|concert|fireworks)\b",
    re.IGNORECASE,
)

_LIST_BY_CATEGORY = re.compile(
    r"\b(any good|show me all|list every|find me all)\b.+\b(leagues|classes|programs|lessons)\b|"
    r"\b(what|any)\b.+\b(leagues)\b.+\b(in|around|near|for)\b|"
    r"\bprograms for\b.+\b(kids|toddlers|teens|children|families)\b|"
    r"\bactivities for kids\b|"
    r"\blist of\b.+\b(classes|programs|lessons)\b|"
    r"\bfind\b.+\b(karate|soccer|swim|tennis|basketball|gymnastics)\b.+\b(classes|programs|lessons|leagues)\b|"
    r"\bwhat\b.+\b(soccer|basketball|tennis|swim)\b.+\b(leagues)\b|"
    r"\bwhat\b.+\b(programs|classes)\b.+\b(exist|available|here|in town|in havasu)\b",
    re.IGNORECASE,
)

# OPEN_NOW disambig — post-F4
_OPEN_NOW_DISAMBIG = re.compile(
    r"(?:"
    r"\bopen now\b|\bopen right now\b|\bcurrently open\b|\bopen at the moment\b|"
    r"\bare you open(?:\s+now)?\b|\bis it open(?:\s+now)?\b|"
    r"^is\s+\w+(?:\s+\w+){0,4}\s+open\s*$|"
    r"\bopen today\b|\bopen tonight\b"
    r")",
    re.IGNORECASE,
)

# OOS triggers — post-F2 (no dining bucket)
_OUT_OF_SCOPE_TRIGGERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "weather",
        (
            "weather",
            "forecast",
            "temperature",
            "how hot",
            "how cold",
            "is it hot",
            "is it cold",
            "what to wear",
            "humidity",
            "rainfall",
            "rain",
            "raining",
            "is it going to rain",
            "going to rain",
        ),
    ),
    (
        "lodging",
        (
            "hotel",
            "motel",
            "airbnb",
            "where to stay",
            "where should i stay",
            "place to stay",
            "places to stay",
            "where can i stay",
            "accommodation",
            "accommodations",
            "lodging",
            "place to sleep",
            "where to sleep",
            "somewhere to stay",
        ),
    ),
    (
        "transportation",
        (
            "directions",
            "how to get to",
            "how to get there",
            "how do i get there",
            "how far",
            "uber",
            "lyft",
            "taxi",
            "parking",
            "where do i park",
            "place to park",
            "rent a car",
            "car rental",
            "nearest airport",
            "closest airport",
            "drive to",
        ),
    ),
)

_EVENT_INDICATOR_WORDS = (
    "event",
    "events",
    "festival",
    "parade",
    "fireworks",
    "tournament",
    "concert",
    "gala",
    "fundraiser",
    "tour",
)

_NIGHT_ACTIVITY_WORDS = (
    "bike",
    "trivia",
    "karaoke",
    "comedy",
    "music",
    "movie",
    "paint",
    "open mic",
)

_COMMERCIAL_EVENT_RESCUE_PHRASES = (
    "rental event",
    "booking event",
    "open house",
    "ribbon cutting",
    "tour event",
    "grand opening",
)


def _commercial_services_query(m: str) -> bool:
    if any(p in m for p in _COMMERCIAL_EVENT_RESCUE_PHRASES):
        return False
    if re.search(r"\b(cheap|affordable)\b", m):
        return True
    if re.search(r"\b(rentals?)\b", m):
        return True
    if re.search(r"\bhire\b", m):
        return True
    if "book a " in m or "book me" in m or "book my " in m:
        return True
    if "venue for" in m:
        return True
    if "birthday party" in m or "wedding venue" in m or "party venue" in m:
        return True
    return False


def detect_out_of_scope_category(message: str) -> str | None:
    m = message.lower()
    if "restaurant week" in m:
        return None
    if "night" in m and any(f"{word} night" in m for word in _NIGHT_ACTIVITY_WORDS):
        return None
    if _commercial_services_query(m):
        return "commercial_services"
    if any(word in m for word in _EVENT_INDICATOR_WORDS):
        return None
    for category, triggers in _OUT_OF_SCOPE_TRIGGERS:
        if any(t in m for t in triggers):
            return category
    return None


# Tier 2 listing predicate — post-F5
_LISTING_PREFIX = re.compile(
    r"^\s*("
    r"where\s+can\s+i\s+(?:find|get)\s+(?:an\s+|a\s+|some\s+)?|"
    r"where(?:'s|\s+is|\s+are)\s+(?:an\s+|a\s+|some\s+)|"
    r"find\s+(?:me\s+)?(?:an\s+|a\s+|some\s+)?|"
    r"show\s+me\s+(?:an\s+|a\s+|some\s+)?|"
    r"give\s+me\s+(?:an\s+|a\s+|some\s+)?|"
    r"list\s+(?:of\s+)?(?:all\s+)?(?:the\s+)?|"
    r"any\s+(?:good\s+)?|"
    r"are\s+there\s+(?:any\s+)?(?:good\s+)?|"
    r"what\s+(?:are\s+)?(?:some\s+|the\s+)?(?:good\s+|best\s+)?|"
    r"got\s+(?:any\s+|a\s+)?(?:good\s+)?|"
    r"recommend\s+(?:me\s+)?(?:an\s+|a\s+|any\s+|some\s+)?(?:good\s+)?"
    r")",
    re.IGNORECASE,
)

_LOCALITY_SUFFIX = re.compile(
    r"\s+(?:in|near|around|by)\s+(?:lhc|lake\s+havasu(?:\s+city)?|here|me|town|the\s+area)\.?\s*$",
    re.IGNORECASE,
)
_TRIM_TAIL = re.compile(r"[?\.!\s]+$")
_EVENT_SHAPE_TOKENS = (
    " this week",
    " this weekend",
    " tonight",
    " today",
    " tomorrow",
    " monday",
    " tuesday",
    " wednesday",
    " thursday",
    " friday",
    " saturday",
    " sunday",
    " happening",
    " event",
    " events",
    " class",
    " classes",
    " program",
    " programs",
    " league",
    " leagues",
    " lesson",
    " lessons",
)


def try_business_listing_shortcut(query: str) -> str | None:
    if not query or not query.strip():
        return None
    nq = query.strip()
    m = _LISTING_PREFIX.match(nq)
    if not m:
        return None
    rest = nq[m.end() :].strip()
    if not rest:
        return None
    cleaned = _LOCALITY_SUFFIX.sub("", rest)
    cleaned = _TRIM_TAIL.sub("", cleaned)
    category = cleaned.strip()
    if not category:
        return None
    low_padded = " " + category.lower()
    if any(tok in low_padded for tok in _EVENT_SHAPE_TOKENS):
        return None
    if len(category.split()) > 3:
        return None
    return category.lower()


# Gap-response — post-F3
_GAP_TIER1_FACTUAL = frozenset(
    {
        "PHONE_LOOKUP",
        "WEBSITE_LOOKUP",
        "RATING_LOOKUP",
        "REVIEW_COUNT_LOOKUP",
        "TIME_LOOKUP",
        "OPEN_NOW",
        "HOURS_LOOKUP",
        "LOCATION_LOOKUP",
        "DATE_LOOKUP",
        "AGE_LOOKUP",
        "COST_LOOKUP",
        "NEXT_OCCURRENCE",
    }
)

_RECOMMENDATION_SHAPED = re.compile(
    r"^\s*("
    r"where\s+should\s+i|"
    r"where\s+can\s+i\s+find|"
    r"where\s+can\s+i\s+get|"
    r"what\s+should\s+i|"
    r"what\s+are\s+(?:some|the)|"
    r"best\s+(?:place|spot|restaurant|cafe|bar)|"
    r"good\s+(?:place|spot|restaurant|cafe|bar)"
    r")\b",
    re.IGNORECASE,
)

# =====================================================================
# Catalog load — real LHC providers from the data pull JSONL
# =====================================================================


def load_provider_names() -> list[str]:
    if not PROVIDERS_JSONL.is_file():
        return []
    names: list[str] = []
    with PROVIDERS_JSONL.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            n = (row.get("display_name") or "").strip()
            if n:
                names.append(n)
    return names


def best_entity_match(query: str, names: list[str]) -> tuple[str, float] | None:
    """Use rapidfuzz token_set_ratio at threshold 75 — same as production entity_matcher.

    The previous Jaccard-style heuristic under-predicted matches; rapidfuzz is the actual
    library used in `app/chat/entity_matcher.py`, so importing it here keeps the shadow
    in lock-step with real classifier behavior.
    """
    try:
        from rapidfuzz import fuzz
    except Exception:
        # Fallback: token-overlap Jaccard. Less accurate but no extra dep.
        return _jaccard_match(query, names)
    nq = normalize(query)
    if not nq:
        return None
    best_name: str | None = None
    best_score = -1.0
    for name in names:
        nm = normalize(name)
        if not nm:
            continue
        score = float(fuzz.token_set_ratio(nq, nm))
        if score > best_score:
            best_score = score
            best_name = name
    if best_name and best_score > 75.0:
        return (best_name, best_score)
    return None


def _jaccard_match(query: str, names: list[str]) -> tuple[str, float] | None:
    nq = normalize(query)
    if not nq:
        return None
    nq_tokens = set(nq.split())
    if not nq_tokens:
        return None
    best: tuple[str, float] | None = None
    for name in names:
        nm = normalize(name)
        nm_tokens = set(nm.split())
        if not nm_tokens:
            continue
        common = nq_tokens & nm_tokens
        if not common:
            continue
        denom = len(nq_tokens) + len(nm_tokens)
        score = 200.0 * len(common) / denom
        if nm_tokens.issubset(nq_tokens):
            score = max(score, 90.0)
        if best is None or score > best[1]:
            best = (name, score)
    if best and best[1] > 75.0:
        return best
    return None


# =====================================================================
# Routing simulation
# =====================================================================


def _count_correct(nq: str) -> int:
    return sum(1 for p in _CORRECT_MARKERS if p.search(nq))


def _count_contribute(nq: str) -> int:
    return sum(1 for p in _CONTRIBUTE_MARKERS if p.search(nq))


def predict_classification(query: str) -> dict[str, Any]:
    raw = query.strip()
    nq = normalize(query)
    if not nq:
        return {"mode": "ask", "sub_intent": "OPEN_ENDED", "confidence": 0.4}

    c_hits = _count_correct(nq)
    co_hits = _count_contribute(nq)

    if c_hits >= 1:
        return {"mode": "correct", "sub_intent": "CORRECTION", "confidence": 0.9}
    if co_hits >= 1:
        return {"mode": "contribute", "sub_intent": "NEW_EVENT", "confidence": 0.8}
    if _GREETING_ONLY.match(nq) and "?" not in raw:
        return {"mode": "chat", "sub_intent": "GREETING", "confidence": 0.9}
    if _SMALL_TALK.match(nq):
        return {"mode": "chat", "sub_intent": "SMALL_TALK", "confidence": 0.85}
    if _REAL_ESTATE_CHAT.search(nq):
        return {"mode": "chat", "sub_intent": "OUT_OF_SCOPE", "confidence": 0.9}
    if detect_out_of_scope_category(raw) is not None:
        return {"mode": "chat", "sub_intent": "OUT_OF_SCOPE", "confidence": 0.88}

    # ask mode — sub_intent
    if _NEXT_OCCURRENCE.search(nq):
        return {"mode": "ask", "sub_intent": "NEXT_OCCURRENCE", "confidence": 0.78}

    for intent_name, pattern in INTENT_PATTERNS:
        if pattern.search(nq):
            if intent_name == "HOURS_LOOKUP" and _OPEN_NOW_DISAMBIG.search(nq):
                return {"mode": "ask", "sub_intent": "OPEN_NOW", "confidence": 0.82}
            return {"mode": "ask", "sub_intent": intent_name, "confidence": 0.88}

    if _LIST_BY_CATEGORY.search(nq):
        return {"mode": "ask", "sub_intent": "LIST_BY_CATEGORY", "confidence": 0.75}
    if _OPEN_NOW_DISAMBIG.search(nq):
        return {"mode": "ask", "sub_intent": "OPEN_NOW", "confidence": 0.7}

    return {"mode": "ask", "sub_intent": "OPEN_ENDED", "confidence": 0.68}


_TIER1_SUB_INTENTS = frozenset(
    {
        "TIME_LOOKUP",
        "HOURS_LOOKUP",
        "PHONE_LOOKUP",
        "LOCATION_LOOKUP",
        "WEBSITE_LOOKUP",
        "COST_LOOKUP",
        "AGE_LOOKUP",
        "DATE_LOOKUP",
        "NEXT_OCCURRENCE",
        "OPEN_NOW",
        "RATING_LOOKUP",
        "REVIEW_COUNT_LOOKUP",
    }
)


def predict_route(query: str, provider_names: list[str]) -> dict[str, Any]:
    cls = predict_classification(query)
    mode = cls["mode"]
    sub = cls["sub_intent"]
    out: dict[str, Any] = {
        **cls,
        "tier_used": "?",
        "predicted_response_shape": "",
        "entity_match": None,
    }

    if mode == "chat":
        out["tier_used"] = "chat"
        if sub == "GREETING":
            out["predicted_response_shape"] = "short greeting (Heya / Hey / etc.)"
        elif sub == "SMALL_TALK":
            out["predicted_response_shape"] = "short acknowledgement"
        else:
            out["predicted_response_shape"] = "OOS reply: 'outside what I cover'"
        return out
    if mode == "contribute":
        out["tier_used"] = "placeholder"
        out["predicted_response_shape"] = "intake placeholder reply"
        return out
    if mode == "correct":
        out["tier_used"] = "placeholder"
        out["predicted_response_shape"] = "correction placeholder reply"
        return out

    # mode == ask
    em = best_entity_match(query, provider_names)
    if em:
        out["entity_match"] = em

    # Tier 1 path: requires entity AND sub_intent in _TIER1_SUB_INTENTS
    if sub in _TIER1_SUB_INTENTS and em is not None:
        out["tier_used"] = "1"
        out["predicted_response_shape"] = f"Tier 1 template for {sub}, entity={em[0]!r}"
        return out

    # Gap response check — post-F3
    if sub in _GAP_TIER1_FACTUAL and em is None:
        if not _RECOMMENDATION_SHAPED.match(query):
            if try_business_listing_shortcut(query) is None:
                out["tier_used"] = "gap_template"
                out["predicted_response_shape"] = (
                    f"gap template for {sub}: 'I don't have ... in the catalog yet. "
                    f"Add it at /contribute ...'"
                )
                return out

    # Tier 2 listing shortcut
    cat = try_business_listing_shortcut(query)
    if cat is not None:
        out["tier_used"] = "2"
        out["predicted_response_shape"] = (
            f"Tier 2 listing — category={cat!r}, deterministic 5-bullet renderer"
        )
        out["listing_category"] = cat
        return out

    # Otherwise Tier 3 (synthesis or LLM-parser-fallback)
    out["tier_used"] = "3"
    out["predicted_response_shape"] = "Tier 3 Haiku synthesis (would call LLM)"
    return out


# =====================================================================
# YAML loader (inline — same as static_check.py)
# =====================================================================


def _load_yaml(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-untyped]

        return list(yaml.safe_load(text) or [])
    except Exception:
        return _inline_yaml(text)


def _inline_yaml(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    list_field: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped.startswith("- ") and indent == 0:
            if current is not None:
                items.append(current)
            current = {}
            list_field = None
            after = stripped[2:]
            if ":" in after:
                k, _, v = after.partition(":")
                current[k.strip()] = _coerce(v.strip())
            continue
        if current is None:
            continue
        if ":" in stripped and indent == 2:
            k, _, v = stripped.partition(":")
            v = v.strip()
            if not v:
                list_field = k.strip()
                current[list_field] = []
                continue
            current[k.strip()] = _coerce(v)
            list_field = None
        elif stripped.startswith("- ") and list_field is not None:
            current[list_field].append(_coerce(stripped[2:].strip()))
    if current is not None:
        items.append(current)
    return items


def _coerce(v: str) -> Any:
    s = v.strip()
    if not s:
        return ""
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        body = s[1:-1].strip()
        if not body:
            return []
        return [_coerce(p.strip()) for p in body.split(",")]
    if s in ("true", "false"):
        return s == "true"
    try:
        return int(s)
    except ValueError:
        return s


# =====================================================================
# Main
# =====================================================================


def main() -> int:
    if not QUESTIONS_PATH.is_file():
        print(f"questions.yaml not found at {QUESTIONS_PATH}", file=sys.stderr)
        return 2

    questions = _load_yaml(QUESTIONS_PATH)
    provider_names = load_provider_names()
    print(f"Loaded {len(provider_names)} provider names from JSONL")
    print(f"Loaded {len(questions)} questions from YAML")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    by_shape: dict[str, list[dict[str, Any]]] = defaultdict(list)
    fail_count = 0
    for q in questions:
        qid = str(q.get("id") or "")
        query = str(q.get("query") or "")
        shape = str(q.get("intent_shape") or "")
        expected_tier = str(q.get("expected_tier") or "")
        notes = q.get("notes") or ""
        prediction = predict_route(query, provider_names)
        observed_tier = prediction.get("tier_used") or ""
        verdict = "PASS" if expected_tier == observed_tier else "FAIL"
        if verdict == "FAIL":
            fail_count += 1
        row = {
            "id": qid,
            "query": query,
            "intent_shape": shape,
            "expected_tier": expected_tier,
            "observed_tier": observed_tier,
            "mode": prediction.get("mode"),
            "sub_intent": prediction.get("sub_intent"),
            "entity": prediction.get("entity_match"),
            "predicted_response_shape": prediction.get("predicted_response_shape"),
            "verdict": verdict,
            "notes": notes,
        }
        rows.append(row)
        by_shape[shape].append(row)

    started = datetime.utcnow().isoformat() + "Z"
    lines: list[str] = [
        "# Voice battery — shadow check report",
        "",
        f"**Generated:** {started}",
        "",
        f"- Total questions: **{len(rows)}**",
        f"- PASS (routing matches expected): **{len(rows) - fail_count}**",
        f"- FAIL (routing mismatch — expected tier ≠ predicted tier): **{fail_count}**",
        "",
        "Routing predicted by inline simulation of post-Slice-F regex patterns.",
        "Entity match uses a token-overlap heuristic against 2,266 LHC provider names",
        "from `scripts/output/places_pull/enrichment_enriched.jsonl`.",
        "",
        "FAILs do not all indicate bugs — many are pre-flagged in `notes` as known gaps",
        "(e.g. dining queries that USED to be OOS now route to OPEN_ENDED, or 'best X'",
        "queries that have no Tier 2 predicate). The report groups by intent_shape so",
        "patterns are visible.",
        "",
        "---",
        "",
    ]

    for shape in sorted(by_shape):
        bucket = by_shape[shape]
        fail_in_bucket = sum(1 for r in bucket if r["verdict"] == "FAIL")
        lines.append(f"## {shape} ({len(bucket)} cases, {fail_in_bucket} FAIL)")
        lines.append("")
        lines.append("| id | query | expected | observed | sub_intent | entity | verdict |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in bucket:
            ent = ""
            em = r.get("entity")
            if em:
                ent = f"{em[0]} ({em[1]:.0f})"
            q = r["query"].replace("|", "\\|")
            if len(q) > 60:
                q = q[:57] + "..."
            lines.append(
                f"| {r['id']} | {q} | {r['expected_tier']} | {r['observed_tier']} | "
                f"{r['sub_intent']} | {ent} | {r['verdict']} |"
            )
        # Detail for FAILs / pre-flagged notes
        details = [r for r in bucket if r["verdict"] == "FAIL" or r["notes"]]
        if details:
            lines.append("")
            lines.append("**Detail:**")
            lines.append("")
            for r in details:
                tag = "FAIL" if r["verdict"] == "FAIL" else "note"
                lines.append(f"- `{r['id']}` ({tag}): {r['query']!r}")
                lines.append(
                    f"  - expected={r['expected_tier']} observed={r['observed_tier']} "
                    f"mode={r['mode']} sub={r['sub_intent']}"
                )
                if r.get("predicted_response_shape"):
                    lines.append(f"  - response shape: {r['predicted_response_shape']}")
                if r["notes"]:
                    lines.append(f"  - note: {r['notes']}")
        lines.append("")

    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_MD.relative_to(REPO_ROOT)}")
    print(f"Total: {len(rows)}, PASS: {len(rows) - fail_count}, FAIL: {fail_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
