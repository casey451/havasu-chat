"""
Backfill program.provider_id by matching program.provider_name to providers.

Prerequisites: providers table populated (Phase 1.3). Only updates rows where
provider_id IS NULL; only writes provider_id and updated_at.

Usage:
  python -m app.db.backfill_program_providers
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import UTC, datetime

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.db.seed_providers import _norm_provider_name

FUZZY_THRESHOLD = 90


@dataclass
class FuzzyLinkRecord:
    program_id: str
    program_provider_name: str
    provider_id: str
    provider_name: str
    score: float


@dataclass
class AmbiguousRecord:
    program_id: str
    program_provider_name: str
    kind: str  # "exact_duplicate" | "fuzzy_multiple"
    candidates: list[tuple[str, float]]  # provider_name, score (100 for exact dup)


@dataclass
class BackfillResult:
    programs_scanned: int = 0
    skipped_already_linked: int = 0
    skipped_no_provider_name: int = 0
    linked_exact: int = 0
    linked_fuzzy: int = 0
    fuzzy_details: list[FuzzyLinkRecord] = field(default_factory=list)
    ambiguous: list[AmbiguousRecord] = field(default_factory=list)
    no_match: list[tuple[str, str]] = field(default_factory=list)  # (program_id, provider_name)
    programs_updated: int = 0


def _print_report(
    result: BackfillResult,
    *,
    linked_count: int,
    unlinked_count: int,
) -> None:
    print("=== Backfill program.provider_id ===")
    print(f"programs scanned: {result.programs_scanned}")
    print(f"already linked (skipped): {result.skipped_already_linked}")
    print(f"no provider_name (skipped): {result.skipped_no_provider_name}")
    print(f"linked via exact match: {result.linked_exact}")
    print(f"linked via fuzzy match (threshold {FUZZY_THRESHOLD}): {result.linked_fuzzy}")
    for rec in result.fuzzy_details:
        print(
            f"  fuzzy link  score={rec.score:.1f}  program={rec.program_provider_name!r}  "
            f"-> provider={rec.provider_name!r}  (program.id={rec.program_id})"
        )
    print(f"ambiguous matches: {len(result.ambiguous)}")
    for amb in result.ambiguous:
        print(f"  program id={amb.program_id}  provider_name={amb.program_provider_name!r}  kind={amb.kind}")
        for cname, sc in amb.candidates:
            print(f"    candidate: {cname!r}  score={sc:.1f}")
    print(f"no match: {len(result.no_match)}")
    for pid, pname in result.no_match:
        print(f"  program id={pid}  provider_name={pname!r}")
    print(f"programs updated this run: {result.programs_updated}")
    print(f"programs with provider_id set (after run): {linked_count}")
    print(f"programs with provider_id null (after run): {unlinked_count}")


def backfill_program_providers(db: Session) -> BackfillResult:
    from app.db.models import Program, Provider

    result = BackfillResult()
    providers: list[Provider] = db.query(Provider).all()
    if not providers:
        raise RuntimeError(
            "providers table is empty — run Phase 1.3 provider seed (app.db.seed_providers) "
            "before backfill_program_providers."
        )

    prov_by_norm: dict[str, list[Provider]] = {}
    for p in providers:
        n = _norm_provider_name(p.provider_name)
        prov_by_norm.setdefault(n, []).append(p)

    programs: list[Program] = db.query(Program).order_by(Program.id).all()
    result.programs_scanned = len(programs)
    now = datetime.now(UTC).replace(tzinfo=None)

    for prog in programs:
        if prog.provider_id is not None:
            result.skipped_already_linked += 1
            continue
        pn = prog.provider_name
        if pn is None or not str(pn).strip():
            result.skipped_no_provider_name += 1
            continue
        pn_str = str(pn).strip()
        norm = _norm_provider_name(pn_str)

        exact_cands = prov_by_norm.get(norm, [])
        if len(exact_cands) == 1:
            prov = exact_cands[0]
            prog.provider_id = prov.id
            prog.updated_at = now
            result.linked_exact += 1
            result.programs_updated += 1
            continue
        if len(exact_cands) > 1:
            result.ambiguous.append(
                AmbiguousRecord(
                    program_id=prog.id,
                    program_provider_name=pn_str,
                    kind="exact_duplicate",
                    candidates=[(p.provider_name, 100.0) for p in exact_cands],
                )
            )
            continue

        scored: list[tuple[Provider, float]] = []
        for prov in providers:
            score = float(
                fuzz.token_set_ratio(pn_str, prov.provider_name),
            )
            if score >= FUZZY_THRESHOLD:
                scored.append((prov, score))
        if len(scored) == 1:
            prov, score = scored[0]
            prog.provider_id = prov.id
            prog.updated_at = now
            result.linked_fuzzy += 1
            result.programs_updated += 1
            result.fuzzy_details.append(
                FuzzyLinkRecord(
                    program_id=prog.id,
                    program_provider_name=pn_str,
                    provider_id=prov.id,
                    provider_name=prov.provider_name,
                    score=score,
                )
            )
        elif len(scored) > 1:
            result.ambiguous.append(
                AmbiguousRecord(
                    program_id=prog.id,
                    program_provider_name=pn_str,
                    kind="fuzzy_multiple",
                    candidates=[(p.provider_name, s) for p, s in scored],
                )
            )
        else:
            result.no_match.append((prog.id, pn_str))

    db.commit()

    linked = db.query(Program).filter(Program.provider_id.isnot(None)).count()
    unlinked = db.query(Program).filter(Program.provider_id.is_(None)).count()
    _print_report(result, linked_count=linked, unlinked_count=unlinked)
    return result


def main(argv: list[str] | None = None) -> int:
    from app.bootstrap_env import ensure_dotenv_loaded
    from app.db.database import SessionLocal, init_db

    ensure_dotenv_loaded()
    parser = argparse.ArgumentParser(description="Backfill program.provider_id from providers")
    parser.parse_args(argv)
    init_db()
    with SessionLocal() as db:
        backfill_program_providers(db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
