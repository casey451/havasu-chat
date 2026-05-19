"""HALT 3 eval-set validator (Phase 7) — CI-runnable gate before disclosure flag flip."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from sqlalchemy.orm import Session

from app.chat import disclosure_render
from app.chat.entity_matcher import extract_catalog_entities_from_text, refresh_entity_matcher
from app.chat.unified_router import route
from app.db.database import SessionLocal

DisclosurePath = Literal["cited", "uncited", "i_dont_know"]
ExpectedTier = Literal["tier1", "tier2", "tier3", "gap_template", "chat", "any"]

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


@dataclass(frozen=True)
class EvalQuerySpec:
    id: str
    query: str
    expected_tier: ExpectedTier
    expected_disclosure_path: DisclosurePath
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
                expected_tier=str(row.get("expected_tier", "any")),  # type: ignore[arg-type]
                expected_disclosure_path=str(row["expected_disclosure_path"]),  # type: ignore[arg-type]
                expected_confabulation_rate=float(row.get("expected_confabulation_rate", 0.0)),
                notes=str(row.get("notes", "")),
            )
        )
    return out


def _classify_disclosure_path(response: str, tier_used: str) -> DisclosurePath:
    if _I_DONT_KNOW_RE.search(response or ""):
        return "i_dont_know"
    if tier_used == "gap_template":
        return "i_dont_know"
    if disclosure_render.is_renderer_enabled():
        decision = disclosure_render.consume_decision()
        if decision is not None and decision.tone_allowlist_passed:
            return "cited"
    if tier_used in ("1", "2", "3"):
        return "cited"
    return "uncited"


def _confabulation_rate(response: str, db: Session, *, query: str = "") -> float:
    refresh_entity_matcher(db)
    mentioned = extract_catalog_entities_from_text(response, db)
    if mentioned:
        return 0.0
    if _I_DONT_KNOW_RE.search(response or ""):
        return 0.0
    probes = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", response or "")
    if not probes:
        return 0.0
    q_low = (query or "").lower()
    novel = [p for p in probes if p.lower() not in q_low]
    if not novel:
        return 0.0
    return min(1.0, len(novel) * 0.25)


def _tier_matches(expected: ExpectedTier, actual: str) -> bool:
    if expected == "any":
        return True
    mapping = {"tier1": "1", "tier2": "2", "tier3": "3"}
    if expected in mapping:
        return actual == mapping[expected]
    return actual == expected


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
        refresh_entity_matcher(session)
        resp = route(
            spec.query,
            "halt3-eval",
            session,
            request_headers=headers,
            query_params=qparams,
            temperature_f_override=stub_temperature_f,
        )
        disc = _classify_disclosure_path(resp.response, resp.tier_used)
        conf = _confabulation_rate(resp.response, session, query=spec.query)
        failures: list[str] = []
        if not _tier_matches(spec.expected_tier, resp.tier_used):
            failures.append(f"tier expected {spec.expected_tier}, got {resp.tier_used}")
        if disc != spec.expected_disclosure_path:
            failures.append(
                f"disclosure expected {spec.expected_disclosure_path}, got {disc}"
            )
        if conf > spec.expected_confabulation_rate + 1e-9:
            failures.append(
                f"confabulation {conf:.2f} > {spec.expected_confabulation_rate}"
            )
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

    cited = [r for r in results if r.spec.expected_disclosure_path == "cited"]
    cited_ok = sum(1 for r in cited if r.disclosure_path == "cited")
    cited_cov = (cited_ok / len(cited)) if cited else 1.0

    missing = [r for r in results if r.spec.expected_confabulation_rate == 0.0]
    max_conf = max((r.confabulation_rate for r in missing), default=0.0)

    all_passed = (
        all(r.passed for r in results)
        and cited_cov >= 1.0
        and max_conf <= 0.0
    )
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
