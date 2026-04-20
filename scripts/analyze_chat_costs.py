"""Read-only analytics for ``chat_logs`` (last 30 days).

Uses the same ``DATABASE_URL`` resolution as the app (via ``app.db.database``):
- Railway Postgres when ``DATABASE_URL`` is set (e.g. production).
- Local SQLite when unset (repo default / pytest temp DB is not used here — run
  from repo root with your dev ``DATABASE_URL`` or default ``events.db``).

No database writes. Prints aggregates to stdout only (no query text).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root on sys.path (``python scripts/...`` does not set PYTHONPATH).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from collections import Counter
from datetime import UTC, datetime, timedelta
from statistics import median

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import ChatLog

WINDOW_DAYS = 30
# Claude Haiku 4.5 list pricing (USD per million tokens) — approximate; adjust if Anthropic changes rates.
INPUT_USD_PER_MILLION = 1.0
OUTPUT_USD_PER_MILLION = 5.0


def _tier3_token_stats(db_rows: list[int]) -> tuple[int, float, float, int, int, int]:
    """Return total, mean, median, min, max, count for non-empty list; else zeros."""
    if not db_rows:
        return 0, 0.0, 0.0, 0, 0, 0
    n = len(db_rows)
    s = sum(db_rows)
    mean = s / n
    med = float(median(db_rows))
    return s, mean, med, min(db_rows), max(db_rows), n


def _mean(xs: list[int]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _estimated_cost_usd(inp: int, out: int) -> float:
    return inp * INPUT_USD_PER_MILLION / 1_000_000 + out * OUTPUT_USD_PER_MILLION / 1_000_000


def main() -> None:
    cutoff = datetime.now(UTC) - timedelta(days=WINDOW_DAYS)

    with SessionLocal() as db:
        base = select(ChatLog).where(ChatLog.created_at >= cutoff)
        rows = db.scalars(base).all()

    if not rows:
        print("No chat_logs rows found in the last 30 days for this database.")
        print("(Set DATABASE_URL to your Railway Postgres URL, or use local SQLite with data.)")
        return

    total = len(rows)
    ts = [r.created_at for r in rows if r.created_at is not None]
    earliest = min(ts) if ts else None
    latest = max(ts) if ts else None

    tier_counts = Counter((r.tier_used or "(null)") for r in rows)
    null_tokens = sum(1 for r in rows if r.llm_tokens_used is None)
    non_null_tokens = sum(1 for r in rows if r.llm_tokens_used is not None)

    tier3_tokens = [r.llm_tokens_used for r in rows if r.tier_used == "3" and r.llm_tokens_used is not None]
    t_sum, t_mean, t_median, t_min, t_max, t_n = _tier3_token_stats(tier3_tokens)

    mode_counts = Counter((r.mode or "(null)") for r in rows)

    tier1_subs = Counter(
        (r.sub_intent or "(null)")
        for r in rows
        if r.tier_used == "1"
    )
    top_subs = tier1_subs.most_common(10)

    print("=== Chat log cost / usage analytics ===")
    print(f"Window: last {WINDOW_DAYS} days (created_at >= cutoff UTC)")
    print(f"Total queries (rows): {total}")
    if earliest and latest:
        print(f"Date range (rows): {earliest.isoformat()} -> {latest.isoformat()}")
    print()

    print("--- Tier distribution (tier_used) ---")
    for tier, c in sorted(tier_counts.items(), key=lambda x: (-x[1], x[0])):
        pct = 100.0 * c / total
        print(f"  {tier}: {c} ({pct:.1f}%)")
    print()

    print("--- llm_tokens_used ---")
    print(f"  NULL (no LLM billable row): {null_tokens}")
    print(f"  non-NULL: {non_null_tokens}")
    print(
        "  Note: Tier 1 / gap_template rows typically have NULL tokens. Tier 2/3 store "
        "``llm_tokens_used`` as input+output (and split columns when migrated)."
    )
    print()

    print("--- Tier 3 token usage (tier_used == '3', llm_tokens_used NOT NULL) ---")
    if t_n == 0:
        print("  No Tier 3 rows with token counts in this window.")
    else:
        print(f"  Rows with tokens: {t_n}")
        print(f"  Total tokens: {t_sum}")
        print(f"  Mean per query: {t_mean:.2f}")
        print(f"  Median per query: {t_median:.2f}")
        print(f"  Min: {t_min}  Max: {t_max}")
        worst_all_output = t_sum * OUTPUT_USD_PER_MILLION / 1_000_000
        worst_all_input = t_sum * INPUT_USD_PER_MILLION / 1_000_000
        mid_5050 = t_sum * (0.5 * INPUT_USD_PER_MILLION + 0.5 * OUTPUT_USD_PER_MILLION) / 1_000_000
        print("  Estimated USD (Haiku 4.5 list rates; combined token field only):")
        print(f"    Worst-case if all tokens billed as output: ${worst_all_output:.4f}")
        print(f"    Worst-case if all tokens billed as input:   ${worst_all_input:.4f}")
        print(f"    50/50 input-output split (illustrative):      ${mid_5050:.4f}")
    print()

    # --- Per-tier split (Phase 4.3): rows with NULL llm_input_tokens are pre-migration or
    # non-LLM paths; we exclude them from input/output means and cost sums, but count them.
    print("--- Per-tier input/output split + estimated cost (Haiku 4.5 rates) ---")
    print(
        "  Rows missing llm_input_tokens/llm_output_tokens are excluded from mean/cost sums "
        "(typically pre-migration data or tiers with no LLM call). ``n_with_split`` counts "
        "rows used for averages; ``n_tier`` is all rows for that tier_used in the window."
    )
    tier_keys = sorted(tier_counts.keys(), key=lambda k: (-tier_counts[k], k))
    for tier in tier_keys:
        tier_rows = [r for r in rows if (r.tier_used or "(null)") == tier]
        n_tier = len(tier_rows)
        split_rows = [
            r
            for r in tier_rows
            if r.llm_input_tokens is not None and r.llm_output_tokens is not None
        ]
        n_split = len(split_rows)
        pre = n_tier - n_split
        if n_split:
            ins = [r.llm_input_tokens for r in split_rows if r.llm_input_tokens is not None]
            outs = [r.llm_output_tokens for r in split_rows if r.llm_output_tokens is not None]
            mean_in = _mean(ins)
            mean_out = _mean(outs)
            cost_sum = sum(
                _estimated_cost_usd(int(r.llm_input_tokens or 0), int(r.llm_output_tokens or 0))
                for r in split_rows
            )
        else:
            mean_in = mean_out = 0.0
            cost_sum = 0.0
        print(f"  tier_used={tier!r}  rows={n_tier}  with_split={n_split}  pre_split_or_null={pre}")
        if n_split:
            print(f"    mean llm_input_tokens:  {mean_in:.2f}")
            print(f"    mean llm_output_tokens: {mean_out:.2f}")
            print(f"    estimated cost (sum):     ${cost_sum:.4f}")
        else:
            print("    (no split-token rows for this tier in window)")
    print()

    print("--- Mode distribution ---")
    for mode, c in sorted(mode_counts.items(), key=lambda x: (-x[1], x[0])):
        pct = 100.0 * c / total
        print(f"  {mode}: {c} ({pct:.1f}%)")
    print()

    print("--- Top sub_intent (tier_used == '1' only) ---")
    if not tier1_subs:
        print("  No Tier 1 rows in this window.")
    else:
        for sub, c in top_subs:
            pct = 100.0 * c / sum(tier1_subs.values())
            print(f"  {sub}: {c} ({pct:.1f}% of Tier-1 rows)")


if __name__ == "__main__":
    main()
