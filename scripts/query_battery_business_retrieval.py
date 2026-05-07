"""Query battery for the Slice A–D business retrieval work.

Exercises a representative set of queries against the live unified router and
asserts each one lands on the expected tier with the expected token cost. The
guarantee from the brief: factual lookups (Tier 1) consume zero AI tokens; simple
business listings (Tier 2 shortcut) consume zero AI tokens; only synthesis-shaped
queries (Tier 3) burn Haiku.

Run from PowerShell with the venv active and the local SQLite DB seeded with at
least one Google-sourced provider (any of the 2,266 already loaded works). The
script makes ZERO Anthropic calls for Tier 1/2 cases by design — it only spends
tokens on the explicit Tier 3 cases at the bottom, and even those can be skipped
with --skip-tier3 to keep the run free.

Usage:
    python -m scripts.query_battery_business_retrieval
    python -m scripts.query_battery_business_retrieval --skip-tier3
    python -m scripts.query_battery_business_retrieval --provider "Mudshark Brewing Company"

The provider override is useful when the local DB doesn't contain the canonical
sample names referenced in the battery — pass any real provider_name from your
providers table and the script substitutes it into the entity-bound queries.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select

from app.chat.unified_router import ChatResponse, route
from app.db.database import SessionLocal
from app.db.models import Provider


@dataclass(frozen=True)
class Case:
    """One query the battery runs."""

    label: str
    query: str  # may contain "{provider}" — substituted with the chosen sample provider
    expected_tier: str  # "1" | "2" | "3" | "gap_template" | "chat"
    expect_zero_tokens: bool
    requires_provider: bool = False  # True when the query needs an entity match


# Tier 1 — factual lookups. Zero tokens. Each one substitutes {provider} with a real name.
TIER1_CASES: list[Case] = [
    Case("phone", "phone number for {provider}", "1", True, requires_provider=True),
    Case("address", "address for {provider}", "1", True, requires_provider=True),
    Case("website", "website for {provider}", "1", True, requires_provider=True),
    Case("hours", "what are the hours for {provider}", "1", True, requires_provider=True),
    Case("open_now", "is {provider} open right now", "1", True, requires_provider=True),
    Case("rating", "what is the rating for {provider}", "1", True, requires_provider=True),
    Case("review_count", "how many reviews does {provider} have", "1", True, requires_provider=True),
]

# Tier 2 — listing shortcut. Zero tokens.
TIER2_CASES: list[Case] = [
    Case("listing_barber", "find me a barber in LHC", "2", True),
    Case("listing_coffee", "any good coffee shops", "2", True),
    Case("listing_haircut", "where can I get a haircut", "2", True),
]

# Tier 3 — synthesis. Tokens > 0 expected. Optional (gated by --skip-tier3).
TIER3_CASES: list[Case] = [
    Case("synthesis_date_night", "where is a good place for date night", "3", False),
    Case("synthesis_kids", "what should I do with kids this weekend", "3", False),
]


def _pick_sample_provider(override: Optional[str]) -> str:
    if override:
        return override.strip()
    with SessionLocal() as db:
        row = db.scalars(
            select(Provider)
            .where(
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
                Provider.google_place_id.is_not(None),
                Provider.phone.is_not(None),
                Provider.address.is_not(None),
                Provider.google_rating.is_not(None),
            )
            .limit(1)
        ).first()
        if row is not None:
            return row.provider_name
        # Fallback: any provider with phone + address
        row = db.scalars(
            select(Provider)
            .where(
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
                Provider.phone.is_not(None),
                Provider.address.is_not(None),
            )
            .limit(1)
        ).first()
        if row is None:
            raise RuntimeError(
                "No suitable provider found in DB. Pass --provider <name> with a real provider_name."
            )
        return row.provider_name


def _run_one(case: Case, provider_name: str) -> ChatResponse:
    q = case.query.format(provider=provider_name)
    with SessionLocal() as db:
        return route(q, session_id=None, db=db)


def _format_token_cost(resp: ChatResponse) -> str:
    if resp.llm_tokens_used is None:
        return "n/a"
    return f"{resp.llm_input_tokens or 0}+{resp.llm_output_tokens or 0}={resp.llm_tokens_used}"


def _run_battery(cases: list[Case], provider_name: str) -> list[tuple[Case, ChatResponse, list[str]]]:
    results: list[tuple[Case, ChatResponse, list[str]]] = []
    for case in cases:
        try:
            resp = _run_one(case, provider_name)
        except Exception as exc:
            print(f"  [{case.label}] EXCEPTION: {exc}")
            raise
        failures: list[str] = []
        if resp.tier_used != case.expected_tier:
            failures.append(f"tier_used={resp.tier_used} expected={case.expected_tier}")
        if case.expect_zero_tokens:
            tokens_seen = resp.llm_tokens_used or 0
            if tokens_seen > 0:
                failures.append(f"non-zero tokens: {tokens_seen}")
        else:
            if (resp.llm_tokens_used or 0) == 0:
                failures.append("expected synthesis tokens, got 0")
        results.append((case, resp, failures))
    return results


def _print_results(label: str, results: list[tuple[Case, ChatResponse, list[str]]]) -> tuple[int, int]:
    passes = 0
    fails = 0
    print(f"\n=== {label} ({len(results)} cases) ===")
    for case, resp, failures in results:
        status = "PASS" if not failures else "FAIL"
        if failures:
            fails += 1
        else:
            passes += 1
        cost = _format_token_cost(resp)
        head = f"  [{status}] {case.label:18s} tier={resp.tier_used:14s} tokens={cost:>14s}"
        print(head + f"  q={case.query!r}")
        if failures:
            for f in failures:
                print(f"    -> {f}")
            preview = (resp.response or "").strip().replace("\n", " ")[:140]
            print(f"    response: {preview!r}")
    return passes, fails


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--provider", help="Override the sample provider_name used in entity-bound queries.")
    p.add_argument("--skip-tier3", action="store_true", help="Skip Tier 3 cases (no token spend).")
    args = p.parse_args()

    provider_name = _pick_sample_provider(args.provider)
    print(f"Using sample provider: {provider_name!r}")

    total_pass = 0
    total_fail = 0

    t1_results = _run_battery(TIER1_CASES, provider_name)
    p1, f1 = _print_results("Tier 1 — factual lookups (zero-token target)", t1_results)
    total_pass += p1
    total_fail += f1

    t2_results = _run_battery(TIER2_CASES, provider_name)
    p2, f2 = _print_results("Tier 2 — business-listing shortcut (zero-token target)", t2_results)
    total_pass += p2
    total_fail += f2

    if args.skip_tier3:
        print("\nSkipping Tier 3 cases (--skip-tier3).")
    else:
        t3_results = _run_battery(TIER3_CASES, provider_name)
        p3, f3 = _print_results("Tier 3 — synthesis (tokens expected)", t3_results)
        total_pass += p3
        total_fail += f3

    print(f"\nSummary: {total_pass} pass, {total_fail} fail")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
