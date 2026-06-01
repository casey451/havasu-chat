"""HALT 3 eval-set validator (Phase 7) — CI-runnable gate before disclosure flag flip."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from sqlalchemy.orm import Session

from app.chat import disclosure_render
from app.chat.entity_matcher import (
    ensure_entity_matcher,
    extract_catalog_entities_from_text,
)
from app.chat.unified_router import route
from app.db.database import SessionLocal
from app.db.models import Provider

DisclosurePath = Literal["cited", "uncited", "i_dont_know"]
DisclosurePathField = DisclosurePath | list[DisclosurePath]
ExpectedTier = Literal["tier1", "tier2", "tier3", "gap_template", "chat"]
ExpectedTierField = ExpectedTier | list[ExpectedTier]

_I_DONT_KNOW_RE = re.compile(
    r"\b(?:"
    r"i\s+don'?t\s+(?:know|have)|"
    r"i'?m\s+not\s+aware|"
    r"not\s+in\s+(?:the\s+)?catalog|"
    r"no\s+data\s+on|"
    r"don'?t\s+have\s+(?:any|that|those|a|an)\b|"
    r"no\s+\w+(?:\s+\w+){0,4}\s+listed"
    r")\b",
    re.IGNORECASE,
)

_PHONE_RE = re.compile(r"\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}")
_ADDRESS_RE = re.compile(
    r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?[A-Z][\w.]*"
    r"(?:\s+[A-Z][\w.]*){0,4}\s+(?:Blvd|Ave|St|Rd|Dr|Ln|Way|Hwy|Pl)\b"
)
_HOURS_RE = re.compile(
    r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|daily|today|tomorrow)\w*"
    r"[^.]*?\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM|–|-)"
)
_RATING_RE = re.compile(r"\b[1-5](?:\.\d)?\s*(?:stars?|/\s*5)\b", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+")
_EMAIL_RE = re.compile(r"\b[\w.+\-]+@[\w\-]+\.\w+\b")

# Platform / contribute URLs are not business-confab signals.
# Phase 7.5.4 — tightened: anchored hostname + path-segment patterns.
# - golakehavasu.com must be the host (or subdomain): require '//' or '.' before it
#   and a '/', ':', '?', '#', or end-of-string after the TLD.
# - /contribute must be a path component: require it preceded by host or '/' and
#   followed by '/', '?', '#', or end-of-string (NOT a substring of /contribute-please).
_PLATFORM_URL_RE = re.compile(
    r"(?:^|//|\.)golakehavasu\.com(?:[/:?#]|$)"
    r"|(?:^|/)contribute(?:[/?#]|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EvalQuerySpec:
    id: str
    query: str
    expected_tier: ExpectedTierField
    expected_disclosure_path: DisclosurePathField
    expected_confabulation_rate: float
    notes: str = ""


@dataclass
class EvalQueryResult:
    spec: EvalQuerySpec
    tier_used: str
    disclosure_path: DisclosurePath
    confabulation_rate: float
    response_excerpt: str
    passed: bool
    failure_reasons: list[str] = field(default_factory=list)


@dataclass
class EvalSetReport:
    results: list[EvalQueryResult]
    cited_disclosure_coverage: float
    missing_data_max_confabulation: float
    all_passed: bool


def _coerce_expected_tier(raw_val: object) -> ExpectedTierField:
    if isinstance(raw_val, list):
        return [str(x) for x in raw_val]  # type: ignore[list-item, return-value]
    return str(raw_val) if raw_val is not None else "any"  # type: ignore[return-value]


def _coerce_disclosure_path(raw_val: object) -> DisclosurePathField:
    """Phase 7.7.1: accept either a scalar path or a list-or-allowlist of paths
    (mirrors _coerce_expected_tier). The list form supports rows like q10/q12
    where the Phase 7.7 honest-empty template legitimately shifts the
    classification between `cited` (tier-2 listing) and `i_dont_know`
    (honest-empty template body matches _I_DONT_KNOW_RE)."""
    if isinstance(raw_val, list):
        return [str(x) for x in raw_val]  # type: ignore[list-item, return-value]
    return str(raw_val) if raw_val is not None else "uncited"  # type: ignore[return-value]


def load_eval_set(path: str | Path) -> list[EvalQuerySpec]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("eval set must be a YAML list")
    out: list[EvalQuerySpec] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        out.append(
            EvalQuerySpec(
                id=str(row["id"]),
                query=str(row["query"]),
                expected_tier=_coerce_expected_tier(row.get("expected_tier")),
                expected_disclosure_path=_coerce_disclosure_path(row["expected_disclosure_path"]),
                expected_confabulation_rate=float(row.get("expected_confabulation_rate", 0.0)),
                notes=str(row.get("notes", "")),
            )
        )
    return out


def _is_platform_url(url: str) -> bool:
    return bool(_PLATFORM_URL_RE.search(url or ""))


# Phase 7.5.4 — per-sentence disclaimer patterns for hours scrub. A captured
# hours probe is scrubbed only if it appears in a sentence that ALSO matches
# one of these hedging-verb + "open tomorrow" co-occurrence shapes.
_HOURS_DISCLAIMER_PATTERNS = (
    re.compile(r"\b(?:can'?t|cannot)\s+say\b[^.!?]*\bopen\s+tomorrow\b", re.I),
    re.compile(r"\b(?:don'?t|do\s+not)\s+(?:know|have)\b[^.!?]*\bopen\s+tomorrow\b", re.I),
    re.compile(r"\b(?:not\s+sure|unclear)\b[^.!?]*\bopen\s+tomorrow\b", re.I),
)

# Phase 7.5.4 — per-sentence disclaimer patterns for rating scrub. A captured
# rating value is scrubbed only if it appears in a sentence that ALSO matches
# one of these template-disclaimer shapes. Replaces the whole-text substring
# gate "rating for" / "rated above" / "stars in the catalog" that wiped the
# entire rating list on q25-shape user-query echoes.
_RATING_DISCLAIMER_PATTERNS = (
    re.compile(
        r"\b(?:don'?t|do\s+not)\s+have\b[^.!?]*\brating\s+for\b",
        re.I,
    ),
    re.compile(
        r"\bno\s+rating\b[^.!?]*\b(?:for|on|available)\b",
        re.I,
    ),
    re.compile(
        r"\bnot\s+in\s+(?:the\s+)?catalog\b[^.!?]*\brating\s+for\b",
        re.I,
    ),
    re.compile(r"\bno\s+\w+(?:\s+\w+){0,4}\s+rated\s+above\b", re.I),
    re.compile(r"\b\d\s+stars?\s+in\s+the\s+catalog\b", re.I),
)


def _sanitize_typed_facts(text: str, facts: dict[str, list[str]]) -> dict[str, list[str]]:
    """Drop template-echo probes that are not business-confab signals.

    Phase 7.5.4: per-sentence scrubs anchored on template-disclaimer shapes.
    User-query echoes ("the rating for X is N.N stars", "X is open tomorrow at
    8am") are NOT scrubbed — only sentences that ALSO match a disclaimer
    pattern have their typed-fact values dropped.
    """
    out = {k: list(v) for k, v in facts.items()}
    sentences = re.split(r"(?<=[.!?])\s+", text or "")

    if out.get("hours"):
        kept_hours: list[str] = []
        for h in out["hours"]:
            in_disclaimer = False
            for s in sentences:
                if h in s and any(p.search(s) for p in _HOURS_DISCLAIMER_PATTERNS):
                    in_disclaimer = True
                    break
            if not in_disclaimer:
                kept_hours.append(h)
        out["hours"] = kept_hours

    if out.get("rating"):
        kept_rating: list[str] = []
        for r in out["rating"]:
            in_disclaimer = False
            for s in sentences:
                if r in s and any(p.search(s) for p in _RATING_DISCLAIMER_PATTERNS):
                    in_disclaimer = True
                    break
            if not in_disclaimer:
                kept_rating.append(r)
        out["rating"] = kept_rating

    return out


def _typed_fact_probes(text: str) -> dict[str, list[str]]:
    """Return per-class lists of typed-fact strings extracted from text."""
    s = text or ""
    urls = [u for u in _URL_RE.findall(s) if not _is_platform_url(u)]
    raw = {
        "phone": _PHONE_RE.findall(s),
        "address": _ADDRESS_RE.findall(s),
        "hours": _HOURS_RE.findall(s),
        "rating": _RATING_RE.findall(s),
        "url": urls,
        "email": _EMAIL_RE.findall(s),
    }
    return _sanitize_typed_facts(s, raw)


def _digits_only(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _entity_has_hours(row: Provider) -> bool:
    if getattr(row, "hours", None):
        return True
    if getattr(row, "hours_structured", None):
        return True
    if getattr(row, "google_hours", None):
        return True
    return False


def _value_matches_any_entity(cls: str, value: str, rows: list[Provider]) -> bool:
    """One typed-fact value vs the list of supporting entity rows."""
    if cls == "phone":
        target = _digits_only(value)
        for r in rows:
            if _digits_only(getattr(r, "phone", "") or "") == target:
                return True
        return False
    if cls == "rating":
        m = re.search(r"\b([1-5](?:\.\d)?)\b", value)
        if not m:
            return False
        asserted = float(m.group(1))
        for r in rows:
            gr = getattr(r, "google_rating", None)
            if gr is not None and abs(float(gr) - asserted) < 0.05:
                return True
        return False
    if cls == "url":
        v_low = value.lower().rstrip("/").rstrip(".")
        for r in rows:
            site = (getattr(r, "website", "") or "").lower().rstrip("/").rstrip(".")
            if site and (site == v_low or site in v_low or v_low in site):
                return True
        return False
    if cls == "address":
        v_low = value.lower()
        for r in rows:
            addr = (getattr(r, "address", "") or "").lower()
            if addr and (addr in v_low or v_low in addr):
                return True
        return False
    if cls == "hours":
        for r in rows:
            if _entity_has_hours(r):
                return True
        return False
    if cls == "email":
        v_low = value.lower()
        for r in rows:
            em = (getattr(r, "email", "") or "").lower()
            if em and em == v_low:
                return True
        return False
    return False


def _entity_supports_typed_facts(
    entity_ids: list[str],
    facts: dict[str, list[str]],
    db: Session,
) -> bool:
    """True if every typed fact can be reconciled with one of the catalog entities."""
    flat = [v for vs in facts.values() for v in vs]
    if not flat:
        return True
    if not entity_ids:
        return False
    rows = db.query(Provider).filter(Provider.id.in_(entity_ids)).all()
    for cls, values in facts.items():
        for v in values:
            if not _value_matches_any_entity(cls, v, rows):
                return False
    return True


def _honest_prefix_clears_response(text: str) -> bool:
    """True iff I-don't-know is in sentence 1 AND tail has no typed facts / novel proper nouns."""
    s = (text or "").strip()
    if not s:
        return False
    sentences = re.split(r"(?<=[.!?])\s+", s)
    if not sentences:
        return False
    first = sentences[0]
    match = _I_DONT_KNOW_RE.search(first)
    if not match:
        return False
    # Typed facts in the same sentence after the disclaimer (comma-spliced confab).
    same_sentence_tail = first[match.end() :]
    if same_sentence_tail.strip():
        tail_facts_first = _typed_fact_probes(same_sentence_tail)
        if any(tail_facts_first.values()):
            return False
        if _has_novel_proper_nouns(same_sentence_tail):
            return False
    if len(sentences) == 1:
        return True
    tail = " ".join(sentences[1:])
    if not tail.strip():
        return True
    tail_facts = _typed_fact_probes(tail)
    if any(tail_facts.values()):
        return False
    return not _has_novel_proper_nouns(tail)


def _has_novel_proper_nouns(text: str) -> bool:
    probes = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text or "")
    locale_noise = {"lake havasu", "lake havasu city", "google business"}
    return any(p.lower() not in locale_noise for p in probes)


def _classify_disclosure_path(
    response: str,
    tier_used: str,
    *,
    db: Session | None = None,
) -> DisclosurePath:
    """Classify the disclosure path of a chat response."""
    text = response or ""
    if _honest_prefix_clears_response(text):
        return "i_dont_know"
    if tier_used == "gap_template":
        return "i_dont_know"
    if disclosure_render.is_renderer_enabled():
        decision = disclosure_render.consume_decision()
        if decision is not None and decision.tone_allowlist_passed:
            return "cited"
    if tier_used in ("1", "2", "3"):
        if db is not None:
            try:
                ensure_entity_matcher(db)
                mentioned = extract_catalog_entities_from_text(text, db)
                if mentioned:
                    return "cited"
                facts = _typed_fact_probes(text)
                if any(facts.values()):
                    return "uncited"
            except Exception:
                logging.exception("_classify_disclosure_path: G5 evidence probe failed")
        return "uncited"
    return "uncited"


def _confabulation_rate(response: str, db: Session, *, query: str = "") -> float:
    """Body-content confabulation score in [0.0, 1.0]."""
    ensure_entity_matcher(db)
    text = response or ""

    mentioned = extract_catalog_entities_from_text(text, db)
    facts = _typed_fact_probes(text)
    has_typed_facts = any(facts.values())

    if _honest_prefix_clears_response(text):
        return 0.0

    # Multi-entity listings: several catalog hits ground the response body.
    if len(mentioned) >= 2:
        return 0.0

    if has_typed_facts:
        entity_ids = [e.id for e in mentioned] if mentioned else []
        if not _entity_supports_typed_facts(entity_ids, facts, db):
            return 1.0

    if mentioned:
        return 0.0

    probes = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text)
    if not probes:
        return 0.0
    q_low = (query or "").lower()
    mentioned_lower = {(e.name or "").lower() for e in mentioned}
    locale_noise = {"lake havasu", "lake havasu city", "google business"}
    novel = [
        p
        for p in probes
        if p.lower() not in q_low
        and p.lower() not in mentioned_lower
        and p.lower() not in locale_noise
    ]
    if not novel:
        return 0.0
    return min(1.0, len(novel) * 0.25)


def _tier_matches(expected: ExpectedTierField, actual: str) -> bool:
    """Match an actual tier ID against an expected tier or allowlist of tiers."""
    mapping = {"tier1": "1", "tier2": "2", "tier3": "3"}

    def _norm(x: str) -> str:
        return mapping.get(x, x)

    if isinstance(expected, list):
        if not expected:
            return False
        return any(actual == _norm(e) for e in expected)
    if expected == "any":
        logging.warning("halt3 eval set still contains expected_tier='any' — burn-down incomplete")
        return True
    return actual == _norm(expected)


def _disclosure_matches(expected: DisclosurePathField, actual: str) -> bool:
    """Phase 7.7.1: match an actual disclosure path against an expected path or
    allowlist of paths (mirrors _tier_matches). The list form supports rows
    like q10/q12 where the Phase 7.7 honest-empty template legitimately shifts
    the classification between `cited` and `i_dont_know`."""
    if isinstance(expected, list):
        if not expected:
            return False
        return actual in expected
    return actual == expected


def _expected_includes_cited(expected: DisclosurePathField) -> bool:
    """True when the spec's expected disclosure path accepts `cited`.
    Phase 7.7.1: needed for the cited-coverage metric when expected is a list."""
    if isinstance(expected, list):
        return "cited" in expected
    return expected == "cited"


def validate_eval_set(
    eval_set_path: str | Path,
    *,
    stub_temperature_f: float | None = None,
    boat_mode: bool = False,
    db: Session | None = None,
) -> EvalSetReport:
    specs = load_eval_set(eval_set_path)
    headers = {"X-Boat-Mode": "1"} if boat_mode else {}
    qparams = {"boat": "1"} if boat_mode else {}
    results: list[EvalQueryResult] = []

    def _run_one(spec: EvalQuerySpec, session: Session) -> EvalQueryResult:
        # Eval-set semantics: every spec must see an up-to-date index in case
        # a previous spec mutated the catalog. force=True preserves that.
        ensure_entity_matcher(session, force=True)
        resp = route(
            spec.query,
            "halt3-eval",
            session,
            request_headers=headers,
            query_params=qparams,
            temperature_f_override=stub_temperature_f,
        )
        disc = _classify_disclosure_path(resp.response, resp.tier_used, db=session)
        conf = _confabulation_rate(resp.response, session, query=spec.query)
        failures: list[str] = []
        if not _tier_matches(spec.expected_tier, resp.tier_used):
            failures.append(f"tier expected {spec.expected_tier}, got {resp.tier_used}")
        if not _disclosure_matches(spec.expected_disclosure_path, disc):
            failures.append(f"disclosure expected {spec.expected_disclosure_path}, got {disc}")
        if conf > spec.expected_confabulation_rate + 1e-9:
            failures.append(f"confabulation {conf:.2f} > {spec.expected_confabulation_rate}")
        return EvalQueryResult(
            spec=spec,
            tier_used=resp.tier_used,
            disclosure_path=disc,
            confabulation_rate=conf,
            response_excerpt=(resp.response or "")[:240],
            passed=not failures,
            failure_reasons=failures,
        )

    if db is not None:
        for spec in specs:
            results.append(_run_one(spec, db))
    else:
        for spec in specs:
            with SessionLocal() as session:
                results.append(_run_one(spec, session))

    # Phase 7.7.1: include list-form expected paths that contain "cited" as
    # a candidate; a row with expected=[cited, i_dont_know] counts toward
    # cited coverage if its actual is "cited" (the canonical cited-tier path).
    cited = [r for r in results if _expected_includes_cited(r.spec.expected_disclosure_path)]
    cited_ok = sum(
        1 for r in cited if _disclosure_matches(r.spec.expected_disclosure_path, r.disclosure_path)
    )
    cited_cov = (cited_ok / len(cited)) if cited else 1.0

    missing = [r for r in results if r.spec.expected_confabulation_rate == 0.0]
    max_conf = max((r.confabulation_rate for r in missing), default=0.0)

    all_passed = all(r.passed for r in results) and cited_cov >= 1.0 and max_conf <= 0.0
    return EvalSetReport(
        results=results,
        cited_disclosure_coverage=cited_cov,
        missing_data_max_confabulation=max_conf,
        all_passed=all_passed,
    )


def main() -> None:
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "app/chat/halt3_eval_set.yaml"
    report = validate_eval_set(path)
    for row in report.results:
        status = "PASS" if row.passed else "FAIL"
        print(f"{status} {row.spec.id} tier={row.tier_used} disc={row.disclosure_path}")
        for reason in row.failure_reasons:
            print(f"  - {reason}")
    print(
        f"cited_coverage={report.cited_disclosure_coverage:.0%} "
        f"missing_confab_max={report.missing_data_max_confabulation:.2f} "
        f"all_passed={report.all_passed}"
    )
    raise SystemExit(0 if report.all_passed else 1)


if __name__ == "__main__":
    main()
