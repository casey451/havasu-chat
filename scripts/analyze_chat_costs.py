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
# Claude Haiku 4.5 (approximate list pricing; input/output split not stored in chat_logs)
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
        "  Note: Tier 1 paths typically have NULL tokens; Tier 3 stores a combined "
        "token total (input + output + cache-related) per tier3_handler - "
        "input vs output split is not captured in chat_logs."
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
        print("  Estimated USD (Haiku 4.5 list rates; combined token field):")
        print(f"    Worst-case if all tokens billed as output: ${worst_all_output:.4f}")
        print(f"    Worst-case if all tokens billed as input:   ${worst_all_input:.4f}")
        print(f"    50/50 input-output split (illustrative):      ${mid_5050:.4f}")
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
