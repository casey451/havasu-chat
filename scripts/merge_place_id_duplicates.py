"""Track B1 — batch-merge the deterministic place_id duplicate tier.

Two ACTIVE providers sharing one ``google_place_id`` are the same physical
place (a single global identity — the one reason the cross-source audit marks
``auto_merge_eligible``). This script consumes exactly that tier and merges
each pair through the tested primitive ``app.contrib.provider_merge
.merge_providers`` (enriched-record-wins gap-fill, FK repointing, soft-retire,
``attributes.merged_into_slug`` 301 stamp, DedupeResolution record).

The 2026-06-10 prod prep found ZERO pairs in this tier (the
``ux_providers_google_place_id`` partial unique index has been holding the
line), so day one this is future-proofing: machinery for when a bad backfill
or index-bypassing path lets one through. The phone / name+street tiers are
deliberately NOT here — they are human-judgment shapes (multi-location,
parent/department, shared office lines) and belong to the review queue at
/admin/providers/duplicates.

Safety (CLAUDE.md prod-data rules, apply_taxonomy_remap.py pattern):
  * DRY-RUN by default — prints keep/dup, reason, per-pair field-diff, counts.
  * ``--apply`` refuses without ``--confirm``.
  * Before writing: rollback snapshot (JSON) of every touched provider row.
  * All merges in ONE transaction; any failure rolls the batch back.
  * Pairs a human already resolved (dedupe_resolutions) are skipped, as are
    pairs linked by location_group_id / parent_provider_id — human resolution
    always outranks the machine tier.

Usage:
    python scripts/merge_place_id_duplicates.py              # dry run
    python scripts/merge_place_id_duplicates.py --apply --confirm
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def _eligible_pairs(session):
    """auto_merge_eligible (place_id) pairs minus human-resolved/linked ones."""
    from sqlalchemy import select

    from app.db.models import DedupeResolution, Provider, dedupe_pair_key
    from scripts.cross_source_dedup_audit import ProvRow, find_provider_pairs

    rows = [
        ProvRow(
            id=p.id,
            name=p.provider_name or "",
            source=p.source,
            website=p.website,
            phone=p.phone,
            lat=p.lat,
            lng=p.lng,
            google_place_id=p.google_place_id,
            verified=bool(p.verified),
            created_at=p.created_at,
        )
        for p in session.scalars(
            select(Provider).where(Provider.is_active.is_(True), Provider.draft.is_(False))
        )
    ]
    pairs, _shared = find_provider_pairs(rows)
    resolved = {k for (k,) in session.execute(select(DedupeResolution.pair_key)).all()}

    out, skipped_resolved, skipped_linked = [], 0, 0
    by_id = {r.id: r for r in rows}
    providers = {p.id: p for p in session.scalars(select(Provider).where(Provider.id.in_(
        [i for c in pairs for i in (c.keep_id, c.dup_id)] or [""]
    )))}
    for c in pairs:
        if c.reason != "google_place_id" or c.action != "auto_merge_eligible":
            continue
        if dedupe_pair_key(c.keep_id, c.dup_id) in resolved:
            skipped_resolved += 1
            continue
        keep, dup = providers.get(c.keep_id), providers.get(c.dup_id)
        if keep is None or dup is None or c.keep_id not in by_id or c.dup_id not in by_id:
            continue
        linked = (
            (keep.location_group_id and keep.location_group_id == dup.location_group_id)
            or keep.parent_provider_id == dup.id
            or dup.parent_provider_id == keep.id
        )
        if linked:
            skipped_linked += 1
            continue
        out.append(c)
    return out, skipped_resolved, skipped_linked


def _snapshot_row(p) -> dict:
    return {
        "id": p.id,
        "slug": p.slug,
        "provider_name": p.provider_name,
        "is_active": p.is_active,
        "draft": p.draft,
        "pending_review": p.pending_review,
        "source": p.source,
        "google_place_id": p.google_place_id,
        "attributes": p.attributes,
        "entity_id": p.entity_id,
    }


def run(
    *,
    apply: bool = False,
    confirm: bool = False,
    snapshot_dir: Path | None = None,
    session=None,
) -> dict:
    """Plan (and optionally commit) the place_id-tier batch merge."""
    from app.contrib.provider_merge import merge_providers
    from app.db.models import Provider

    snapshot_dir = snapshot_dir or _ROOT
    own_session = session is None
    session = session or SessionLocal()
    counts = {"pairs": 0, "skipped_resolved": 0, "skipped_linked": 0, "merged": 0}
    try:
        print(f"DB target: {_sanitized_target()}\n")
        pairs, skipped_resolved, skipped_linked = _eligible_pairs(session)
        counts["pairs"] = len(pairs)
        counts["skipped_resolved"] = skipped_resolved
        counts["skipped_linked"] = skipped_linked

        if not pairs:
            print("place_id tier: 0 eligible pairs — nothing to merge.")
            print(
                f"(skipped: {skipped_resolved} human-resolved, "
                f"{skipped_linked} linked multi-location/parent)"
            )
            return counts

        # Per-pair dry-run plan: keep_id, drop_id, reason, field-diff.
        print(f"place_id tier: {len(pairs)} eligible pair(s)\n")
        for c in pairs:
            plan = merge_providers(session, keep_id=c.keep_id, dup_id=c.dup_id, dry_run=True)
            diff = ", ".join(plan.gap_filled) or "(no gap-fill)"
            print(f"KEEP {c.keep_id}  [{c.keep_name}]")
            print(f"DROP {c.dup_id}  [{c.dup_name}]  reason={c.reason}")
            print(f"     gap-fill -> keeper: {diff}")
            print(f"     repointed refs: {plan.repointed or '{}'}\n")

        if not apply:
            print(
                f"DRY RUN — nothing written. {len(pairs)} pair(s) would merge. "
                "Show Casey these counts; re-run with --apply --confirm after approval."
            )
            return counts
        if not confirm:
            print(f"\nREFUSING TO WRITE — --apply requires --confirm. Target is "
                  f"{_sanitized_target()}.")
            return counts

        # Rollback snapshot of every provider row we may touch.
        touched: dict[str, dict] = {}
        for c in pairs:
            for pid in (c.keep_id, c.dup_id):
                if pid not in touched:
                    touched[pid] = _snapshot_row(session.get(Provider, pid))
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap_path = snapshot_dir / f"place_id_merge_snapshot_{stamp}.json"
        snap_path.write_text(json.dumps(list(touched.values()), indent=2), encoding="utf-8")
        print(f"rollback snapshot: {snap_path} ({len(touched)} provider rows)")

        # One transaction for the whole batch.
        try:
            for c in pairs:
                merge_providers(session, keep_id=c.keep_id, dup_id=c.dup_id, dry_run=False)
                counts["merged"] += 1
            session.commit()
        except Exception:
            session.rollback()
            print("FAILED — batch rolled back, nothing written.")
            raise
        print(f"APPLIED — {counts['merged']} pair(s) merged in one transaction.")
        return counts
    finally:
        if own_session:
            session.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write (default: dry-run).")
    parser.add_argument("--confirm", action="store_true", help="Required with --apply.")
    args = parser.parse_args(argv)
    run(apply=args.apply, confirm=args.confirm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
