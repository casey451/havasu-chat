"""Gap-template leakage audit (hunt 2026-06-10 §1b / C-PR-5 item 3).

Replays every real-user ``tier_used='gap_template'`` turn from a chat_logs
export through the live intent classifier + ``_catalog_gap_response`` against
a catalog snapshot, and reports:

  still_gaps_answerable   -- plain gap template AND the catalog has matching
                             content (category-confirmed candidates or an
                             entity (near-)match) => FALSE POSITIVE
  did_you_mean            -- the gap path answered with a catalog entity
                             ("Closest match …" / "If you meant …") — the
                             user is pointed at the right listing, not a
                             dead end
  still_gaps_genuine      -- plain gap template and nothing in the catalog
                             matches => correct gap behavior
  no_longer_gaps          -- the current router would not gap this query

Synthetic confabulation-harness probes and the CC e2e feedback row are
excluded (hunt §1b: ~41 of 103 rows in the 06-10 export are harness probes —
the gap template firing on those is CORRECT behavior).

Usage:
  python scripts/gap_leakage_audit.py CHAT_LOGS_CSV PROVIDERS_CSV ENTITIES_CSV

Acceptance (C-PR-5): real-user gap false-positive rate < 20%.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CC_E2E_ROW_ID = "16285a6f-0058-4338-a02c-e31e4a2c59d4"
_SYNTHETIC_RE = re.compile(
    r"fabricated\s+hotel|totally\s+fake|imaginary|some\s+random\s+place|"
    r"zzz|xyz\s*404|\b555\b|nonexistent",
    re.I,
)


def _is_synthetic(row: dict) -> bool:
    if (row.get("id") or "") == CC_E2E_ROW_ID:
        return True
    if (row.get("session_id") or "").startswith("cc-e2e-"):
        return True
    q = row.get("normalized_query") or ""
    if _SYNTHETIC_RE.search(q):
        return True
    # The matcher's structural-fake gate (digit runs in letters, low-vowel
    # long tokens, consonant-run + digits) — same heuristic prod uses to keep
    # junk strings away from did-you-mean.
    from app.chat.entity_matcher import _query_has_structurally_fake_token
    from app.chat.normalizer import normalize

    return _query_has_structurally_fake_token(normalize(q))


def _seed_catalog(db, providers_csv: str, entities_csv: str) -> tuple[int, int]:
    from app.db.models import Entity, Provider

    csv.field_size_limit(10_000_000)
    n = e = 0
    with open(providers_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("is_active") or "t").lower() not in ("t", "true", "1"):
                continue
            if (r.get("draft") or "f").lower() in ("t", "true", "1"):
                continue
            gcs = None
            try:
                raw = json.loads(r.get("google_categories") or "null")
                if isinstance(raw, list):
                    gcs = [t for t in raw if isinstance(t, str)]
            except Exception:
                gcs = None
            db.add(
                Provider(
                    id=r["id"],
                    provider_name=r["provider_name"],
                    category=r.get("category") or "x",
                    slug=r["id"],
                    draft=False,
                    is_active=True,
                    address=r.get("address") or None,
                    google_primary_category=r.get("google_primary_category") or None,
                    google_categories=gcs,
                )
            )
            n += 1
    with open(entities_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("is_active") or "True") not in ("True", "t", "true", "1"):
                continue
            if not r.get("name"):
                continue
            db.add(
                Entity(
                    id=r["id"],
                    entity_type=r.get("entity_type") or "commercial",
                    slug=r.get("slug") or r["id"],
                    name=r["name"],
                )
            )
            e += 1
    db.commit()
    return n, e


def _catalog_answerable(db, query: str) -> bool:
    from app.chat.context_builder import (
        _candidate_providers,
        _category_needles_for_query,
        _category_vocab_terms,
        _provider_relevance,
        _query_tokens,
    )
    from app.chat.entity_matcher import find_near_match, match_entity
    from app.chat.normalizer import spell_correct

    corrected = spell_correct(query)
    tokens = _query_tokens(corrected)
    terms = _category_vocab_terms(corrected)
    needles = _category_needles_for_query(terms)
    if needles:
        cands = _candidate_providers(db, tokens, terms, needles)
        # Category-confirmed only — a bare token hit (an address containing
        # "777") is not "the catalog has the answer".
        if any(_provider_relevance(p, [], needles) > 0 for p in cands):
            return True
    if match_entity(query, db) is not None:
        return True
    return find_near_match(query, db) is not None


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) != 3:
        print(__doc__)
        return 2
    chat_logs_csv, providers_csv, entities_csv = args

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.chat.entity_matcher as em
    from app.chat.intent_classifier import classify
    from app.chat.unified_router import _catalog_gap_response
    from app.db.database import Base

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    n, e = _seed_catalog(db, providers_csv, entities_csv)
    em.reset_entity_matcher()
    print(f"catalog: {n} providers, {e} entities")

    csv.field_size_limit(10_000_000)
    with open(chat_logs_csv, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("tier_used") or "") == "gap_template"]
    synthetic = [r for r in rows if _is_synthetic(r)]
    real = [r for r in rows if not _is_synthetic(r)]
    print(f"gap_template rows: {len(rows)} total, {len(synthetic)} synthetic excluded, {len(real)} real-user")

    still_fp: list[str] = []
    still_genuine: list[str] = []
    fixed: list[str] = []
    did_you_mean: list[str] = []
    from app.chat.unified_router import _enrich_entity_from_db

    for r in real:
        q = (r.get("normalized_query") or "").strip()
        if not q:
            continue
        intent = classify(q)
        # Mirror route(): entity enrichment (listing shortcuts, DB-backed
        # fuzzy match, pronoun referents) runs BEFORE the gap check.
        intent = _enrich_entity_from_db(q, intent, db, session=None, current_turn=None)
        gap = _catalog_gap_response(intent, db)
        if gap is None:
            fixed.append(q)
        elif gap.startswith("Closest match in the catalog is") or "If you meant a different" in gap:
            did_you_mean.append(q)
        elif _catalog_answerable(db, q):
            still_fp.append(q)
            if "--verbose" in sys.argv:
                from app.chat.entity_matcher import find_near_match

                near = find_near_match(q, db)
                print(
                    f"FP {q!r}\n   sub={intent.sub_intent} entity={intent.entity!r} "
                    f"near={near}\n   gap_head={gap[:90]!r}"
                )
        else:
            still_genuine.append(q)

    total_real = len(still_fp) + len(still_genuine) + len(fixed) + len(did_you_mean)
    rate = (len(still_fp) / total_real * 100) if total_real else 0.0
    print(f"\nno_longer_gaps:        {len(fixed)}")
    print(f"did_you_mean answered: {len(did_you_mean)}")
    print(f"still_gaps_genuine:    {len(still_genuine)}")
    print(f"still_gaps_answerable: {len(still_fp)}  (FALSE POSITIVES)")
    print(f"real-user gap false-positive rate: {rate:.1f}%  (acceptance: < 20%)")
    if still_fp:
        print("\nfalse positives:")
        for q in sorted(set(still_fp)):
            print("  ", q)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
