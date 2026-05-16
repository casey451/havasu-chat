"""Phase 5.4 §3 diagnostic — print top-3 NPI match scores per
health-wellness-care provider, to understand why scripts/npi_verify.py
reported 0/20 matched on first dry-run.

Loads the NPI registry once for Lake Havasu City + AZ, then for each
health-wellness-care provider prints the top 3 match scores against
NPI entries' names. Surfaces:

  - Whether the LHC NPI dataset contains the practitioner at all
  - What the actual best-match score is (vs the threshold 86)
  - What DBA vs legal-name mismatches look like

Reusable for Phase 5.5+ if NPI verification surfaces again (e.g., for
beauty-personal-care if cosmetic medspa NPIs need matching).
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import httpx
from rapidfuzz import fuzz, utils

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "events.db"

sys.path.insert(0, str(ROOT))
from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.contrib.npi_client import fetch_npi_results_for_city  # noqa: E402
from scripts.npi_verify import _npi_candidate_names  # noqa: E402

CITY = "Lake Havasu City"
STATE = "AZ"
LIMIT = 25  # how many providers to inspect
TOP_K = 3   # how many NPI matches to print per provider


def main() -> int:
    print(f"[npi-diag] fetching NPI registry for {CITY}, {STATE} ...")
    with httpx.Client() as client:
        registry = fetch_npi_results_for_city(client, city=CITY, state=STATE)
    print(f"[npi-diag] NPI registry: {len(registry)} entries")

    # Sample NPI name shapes
    print("\n=== sample NPI name shapes (first 10 entries) ===")
    for i, entry in enumerate(registry[:10]):
        et = entry.get("enumeration_type", "?")
        names = _npi_candidate_names(entry)
        num = entry.get("number", "?")
        first_name = names[0] if names else "(no name)"
        print(f"  [{i:2d}] {et}  NPI={num}  {first_name!r}")

    # Pull health-wellness-care providers
    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()
    rows = list(cur.execute("""
        SELECT p.provider_name, p.google_primary_category, p.id
        FROM providers p
        JOIN entity_categories ec ON ec.entity_id = p.entity_id
        JOIN categories c ON c.id = ec.category_id
        WHERE c.slug = 'health-wellness-care'
        ORDER BY p.provider_name
        LIMIT ?
    """, (LIMIT,)))

    print(f"\n=== top-{TOP_K} NPI match per provider (first {LIMIT} alphabetical) ===")
    print("THRESHOLD=86; rows where best_score >= 86 would be auto-matched.\n")
    matches_at_threshold = 0
    matches_at_80 = 0
    matches_at_70 = 0
    for prov_name, gprimary, pid in rows:
        scores: list[tuple[int, str, str]] = []
        for entry in registry:
            for cand in _npi_candidate_names(entry):
                # Mirror scripts/npi_verify._best_npi_match: token_sort_ratio
                # (not token_set_ratio -- the latter has a subset-100% trap
                # documented in the script) with processor=utils.default_process
                # for case + punctuation normalization.
                s = int(
                    fuzz.token_sort_ratio(
                        prov_name, cand, processor=utils.default_process
                    )
                )
                scores.append((s, cand, str(entry.get("number", ""))))
        scores.sort(key=lambda t: -t[0])
        top = scores[:TOP_K]
        best = top[0][0] if top else 0
        flag = ""
        if best >= 86:
            matches_at_threshold += 1
            flag = "  <-- MATCH (>=86)"
        elif best >= 80:
            matches_at_80 += 1
            flag = "  <-- near-miss (80-85)"
        elif best >= 70:
            matches_at_70 += 1
            flag = "  <-- near (70-79)"
        print(f"  PROVIDER: {prov_name!r}  ({gprimary})")
        for s, cand, num in top:
            print(f"    {s:3d}  NPI={num}  {cand!r}")
        if flag:
            print(f"   {flag}")
        print()

    print("=== match-rate summary ===")
    print(f"  matched (>=86):     {matches_at_threshold} / {len(rows)}")
    print(f"  near-miss (80-85): {matches_at_80} / {len(rows)}")
    print(f"  near (70-79):      {matches_at_70} / {len(rows)}")
    print()
    print("Interpretation:")
    print("  If many near-miss (80-85) hits exist, threshold might be too strict;")
    print("  consider lowering to ~80 for V1 with spot-check confirmation.")
    print("  If most are <70, DBA names don't match individual NPI names --")
    print("  practice-to-practitioner DBA mapping needed (kickoff §3 gotcha).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
