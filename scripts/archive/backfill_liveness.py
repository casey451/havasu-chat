"""Backfill ``newest_review_at`` + ``liveness_score`` from the Places pull.

Reads ``scripts/output/places_pull/enrichment_raw.jsonl`` (the raw Google Places
API payloads, pull of 2026-05-18), extracts the newest review ``publishTime`` and
recomputes the 0–1 liveness blend, then writes both onto matched providers and
mirrors ``liveness_score`` onto the linked entity.

Matching is on ``google_place_id`` against ``providers.google_place_id`` and,
for backfilled Places rows, ``locations.google_place_id`` (entity → provider).

Idempotent and re-runnable. Per CLAUDE.md, **always** dry-run first, show the
counts, and wait for Casey's explicit approval before the real run against prod.

Usage (Windows / PowerShell):

    .venv\\Scripts\\python.exe scripts\\backfill_liveness.py --dry-run
    .venv\\Scripts\\python.exe scripts\\backfill_liveness.py            # writes
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Repo root on sys.path (``python scripts/...`` does not set PYTHONPATH).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.liveness import compute_liveness, liveness_tier  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Entity, Location, Provider  # noqa: E402
from scripts.places_load import _parse_google_publish_time  # noqa: E402

DEFAULT_INPUT_PATH = Path(__file__).parent / "output" / "places_pull" / "enrichment_raw.jsonl"


def _newest_review_at_from_raw(response: dict[str, Any]) -> datetime | None:
    """Max ``publishTime`` across the raw response's ``reviews`` list (or None)."""
    times: list[datetime] = []
    for review in response.get("reviews") or []:
        if not isinstance(review, dict):
            continue
        dt = _parse_google_publish_time(review.get("publishTime"))
        if dt is not None:
            times.append(dt)
    return max(times) if times else None


def _signals_from_row(row: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Return ``(place_id, signals)`` where signals = rating/review_count/newest.

    ``None`` when the row carries no usable ``place_id``.
    """
    place_id = row.get("place_id")
    response = row.get("response") if isinstance(row.get("response"), dict) else {}
    if not place_id:
        return None
    return place_id, {
        "rating": response.get("rating"),
        "review_count": response.get("userRatingCount"),
        "newest_review_at": _newest_review_at_from_raw(response),
    }


def load_signals(path: Path) -> dict[str, dict[str, Any]]:
    """Map ``google_place_id`` -> liveness signals from the raw enrichment file."""
    signals: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parsed = _signals_from_row(json.loads(line))
        if parsed is not None:
            place_id, sig = parsed
            signals[place_id] = sig
    return signals


def run(*, input_path: Path, dry_run: bool = False, ref_now: datetime | None = None) -> Counter:
    ref_now = ref_now or datetime.now(UTC)
    signals = load_signals(input_path)
    counts: Counter = Counter()
    counts["jsonl_place_ids"] = len(signals)
    tier_hist: Counter = Counter()

    db = SessionLocal()
    try:
        # provider lookup keyed on google_place_id (legacy column + entity Location).
        prov_by_pid: dict[str, Provider] = {}
        for p in db.query(Provider).filter(Provider.google_place_id.in_(list(signals))).all():
            if p.google_place_id:
                prov_by_pid[p.google_place_id] = p
        for p, loc_pid in (
            db.query(Provider, Location.google_place_id)
            .join(Entity, Provider.entity_id == Entity.id)
            .join(Location, Location.entity_id == Entity.id)
            .filter(Location.google_place_id.in_(list(signals)))
            .all()
        ):
            prov_by_pid.setdefault(loc_pid, p)

        matched_pids = set(prov_by_pid)
        counts["matched"] = len(matched_pids)
        counts["unmatched"] = len(signals) - len(matched_pids)

        for pid, provider in prov_by_pid.items():
            sig = signals[pid]
            newest = sig["newest_review_at"]
            score = compute_liveness(sig["rating"], sig["review_count"], newest, ref_now)
            tier = liveness_tier(sig["rating"], sig["review_count"], newest, ref_now)
            tier_hist[tier] += 1
            changed = (
                provider.newest_review_at != newest or provider.liveness_score != score
            )
            if changed:
                counts["updated"] += 1
            if not dry_run:
                provider.newest_review_at = newest
                provider.liveness_score = score
                ent = db.get(Entity, provider.entity_id) if provider.entity_id else None
                if ent is not None:
                    ent.liveness_score = score

        if not dry_run:
            db.commit()
    finally:
        db.close()

    verb = "would update" if dry_run else "updated"
    print("--- liveness backfill summary ---")
    print(f"place_ids in JSONL:   {counts['jsonl_place_ids']}")
    print(f"matched providers:    {counts['matched']}")
    print(f"unmatched place_ids:  {counts['unmatched']}")
    print(f"{verb}:          {counts['updated']}")
    print("tier distribution (matched):")
    for tier, n in tier_hist.most_common():
        print(f"    {tier}: {n}")
    if dry_run:
        print("[backfill] dry-run complete; no DB writes")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()
    run(input_path=args.input, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
