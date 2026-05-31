"""One-off cleanup: merge existing live duplicate providers (READ-ONLY by default).

This is a reviewed, one-off operational script. It is read-only unless you pass
the explicit ``--apply`` flag. By default it runs as a DRY RUN and changes
nothing.

It is glue code on top of two already-built, reviewed pieces:

  * The audit scoring core in ``scripts.cross_source_dedup_audit`` --
    ``_load_provider_rows`` (the DB loader) and ``find_provider_pairs`` (the
    pure scorer that produces ``CandidatePair`` records).
  * The merge primitive in ``app.contrib.provider_merge`` --
    ``merge_providers(db, *, keep_id, dup_id, dry_run=False) -> MergeResult``,
    which gap-fills the keeper, combines ``source``, repoints foreign keys, and
    soft-retires the loser. The primitive does NOT commit; this caller commits.

By default it targets ONLY the ``geo+name`` reason (the same-source self-dups --
the safe worklist). Widen with ``--reason`` if you know what you are doing.

Run commands (from a real environment that can reach the database)::

    # 1) Dry run -- shows what WOULD happen, writes nothing (DEFAULT):
    python -m scripts.merge_existing_dups

    # 2) Apply for real -- single session, single commit at the end:
    python -m scripts.merge_existing_dups --apply

    # Optional: widen the reason set and/or raise the score floor:
    python -m scripts.merge_existing_dups --reason geo+name,website --min-score 90
    python -m scripts.merge_existing_dups --reason geo+name --reason website --apply

    # Safe website cleanup -- merge ONLY website pairs whose normalized names are
    # IDENTICAL and that are physically close. --require-identical-name alone is
    # NOT enough on prod: same-name CHAIN locations (Subway x3, Dollar General x4,
    # Shell, McDonald's...) share one corporate domain at 3km+ apart and would be
    # wrongly merged. Add --max-distance-m 500 so only truly co-located same-name
    # dups qualify (London Bridge Resort 66m, Sugared in the City 0m) while the
    # chains are excluded:
    python -m scripts.merge_existing_dups --reason website --require-identical-name --max-distance-m 500
    python -m scripts.merge_existing_dups --reason website --require-identical-name --max-distance-m 500 --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Set

# Make the project root importable when run as a bare script (python
# scripts/merge_existing_dups.py), matching the sibling audit script's pattern.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contrib.ingest_reconciler import slugify  # noqa: E402
from app.contrib.provider_merge import merge_providers  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402
from scripts.cross_source_dedup_audit import (  # noqa: E402
    _load_provider_rows,
    find_provider_pairs,
)

# Reasons emitted by the audit scorer. "geo+name" is the safe same-source
# self-dup worklist and is the default target.
VALID_REASONS = ("google_place_id", "website", "phone", "geo+name")
DEFAULT_REASONS = ("geo+name",)


def _parse_reasons(raw: Optional[Sequence[str]]) -> Set[str]:
    """Flatten repeatable + comma-separated --reason values into a clean set."""
    if not raw:
        return set(DEFAULT_REASONS)
    out: Set[str] = set()
    for chunk in raw:
        for token in chunk.split(","):
            token = token.strip()
            if not token:
                continue
            if token not in VALID_REASONS:
                raise SystemExit(
                    "Unknown --reason %r. Valid values: %s"
                    % (token, ", ".join(VALID_REASONS))
                )
            out.add(token)
    return out


def _refetch(session, provider_id: str):
    """Re-fetch a provider in the live session by id (ids are strings)."""
    return session.get(Provider, provider_id)


def _is_resolved(provider) -> bool:
    """True if a re-fetched provider is gone / inactive / already retired.

    A provider that no longer exists, is not active, or has been flipped to
    draft=True (the merge primitive's soft-retire) must not be merged again.
    """
    if provider is None:
        return True
    if not bool(getattr(provider, "is_active", True)):
        return True
    if bool(getattr(provider, "draft", False)):
        return True
    return False


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Merge existing live duplicate providers using the reviewed merge "
            "primitive. READ-ONLY (dry run) unless --apply is passed."
        )
    )
    parser.add_argument(
        "--reason",
        action="append",
        default=None,
        help=(
            "Reason(s) to target. Repeatable and/or comma-separated. "
            "Valid: %s. Default: %s."
            % (", ".join(VALID_REASONS), ", ".join(DEFAULT_REASONS))
        ),
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=None,
        help="Only consider pairs with score >= this value.",
    )
    parser.add_argument(
        "--require-identical-name",
        action="store_true",
        help=(
            "Only consider pairs whose keeper and dup have IDENTICAL normalized "
            "names (slugify(keep)==slugify(dup)). Use with --reason website to "
            "safely merge same-name website self-dups (Express Getaway, Empty "
            "Spaces...) while excluding distinct venues that merely share a domain."
        ),
    )
    parser.add_argument(
        "--max-distance-m",
        type=float,
        default=None,
        help=(
            "Only consider pairs whose two rows are within this many meters. "
            "Pairs with NO distance (a row missing lat/lng) are EXCLUDED when "
            "this is set. Use with --reason website to exclude same-name chain "
            "locations that merely share a corporate domain (Subway, Dollar "
            "General 3km+ apart) while keeping true co-located dups (London "
            "Bridge Resort 66m, Sugared in the City 0m). Suggested: 500."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Actually perform the merges and commit ONCE at the end. "
            "Omit for a dry run (the default)."
        ),
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    reasons = _parse_reasons(args.reason)
    min_score = args.min_score
    apply_mode = bool(args.apply)
    require_identical_name = bool(args.require_identical_name)
    max_distance_m = args.max_distance_m

    mode_label = "APPLY (writes + single commit)" if apply_mode else "DRY RUN (read-only)"
    print("=" * 70)
    print("merge_existing_dups -- %s" % mode_label)
    print("Target reasons: %s" % ", ".join(sorted(reasons)))
    if min_score is not None:
        print("Minimum score:  %s" % min_score)
    if require_identical_name:
        print("Filter: identical normalized names only")
    if max_distance_m is not None:
        print("Filter: distance <= %s m (pairs with no distance excluded)" % max_distance_m)
    print("=" * 70)

    # Snapshot the live rows up front and score them. Pairs are computed from
    # this snapshot, so a merge in one pair can retire a row that appears in a
    # later pair (e.g. 3-way clusters). We guard against that with a re-fetch
    # below before each merge.
    rows = _load_provider_rows(None)
    pairs, _shared = find_provider_pairs(rows)

    def _within_distance(pair: object) -> bool:
        if max_distance_m is None:
            return True
        # No distance (a row is missing coords) cannot be confirmed close, so
        # exclude it under a distance guard -- conservative by design.
        dist = getattr(pair, "distance_m", None)
        return dist is not None and dist <= max_distance_m

    selected = [
        pair
        for pair in pairs
        if pair.reason in reasons
        and (min_score is None or pair.score >= min_score)
        and (
            not require_identical_name
            or slugify(pair.keep_name or "") == slugify(pair.dup_name or "")
        )
        and _within_distance(pair)
    ]

    pairs_considered = len(selected)
    merged = 0
    skipped_already_resolved = 0
    skipped_error = 0
    error_reasons: List[str] = []

    with SessionLocal() as session:
        for pair in selected:
            # Re-fetch both sides in the live session. Skip if either side was
            # already retired by an earlier merge in THIS run (or is otherwise
            # gone / inactive / draft).
            keep = _refetch(session, pair.keep_id)
            dup = _refetch(session, pair.dup_id)
            if _is_resolved(keep) or _is_resolved(dup):
                skipped_already_resolved += 1
                print(
                    "SKIP (already resolved): keep #%s %r <- dup #%s %r"
                    % (pair.keep_id, pair.keep_name, pair.dup_id, pair.dup_name)
                )
                continue

            try:
                result = merge_providers(
                    session,
                    keep_id=pair.keep_id,
                    dup_id=pair.dup_id,
                    dry_run=not apply_mode,
                )
            except ValueError as exc:
                skipped_error += 1
                error_reasons.append(str(exc))
                print(
                    "SKIP (error): keep #%s %r <- dup #%s %r :: %s"
                    % (pair.keep_id, pair.keep_name, pair.dup_id, pair.dup_name, exc)
                )
                continue

            merged += 1
            verb = "WOULD MERGE" if not apply_mode else "MERGED"
            gap_filled = getattr(result, "gap_filled", []) or []
            repointed = getattr(result, "repointed", {}) or {}
            repointed_total = sum(int(v) for v in repointed.values())
            print(
                "%s: keep #%s %r <- dup #%s %r "
                "[reason=%s score=%s dist_m=%s]"
                % (
                    verb,
                    pair.keep_id,
                    pair.keep_name,
                    pair.dup_id,
                    pair.dup_name,
                    pair.reason,
                    pair.score,
                    pair.distance_m,
                )
            )
            print(
                "    gap_filled=%s repointed=%s (total %d) combined_source=%r"
                % (
                    gap_filled,
                    dict(repointed),
                    repointed_total,
                    getattr(result, "combined_source", None),
                )
            )

        if apply_mode:
            if skipped_error and merged == 0:
                # Nothing to commit; still fine to commit a no-op, but make it
                # explicit that no merges succeeded.
                print("No successful merges; committing no changes.")
            session.commit()
            print("Committed %d merge(s) in a single transaction." % merged)
        else:
            # Dry run: roll back any speculative state the primitive may have
            # touched on the session, just to be tidy.
            session.rollback()

    print("-" * 70)
    print("SUMMARY (%s)" % mode_label)
    print("  pairs_considered:          %d" % pairs_considered)
    print("  merged:                    %d" % merged)
    print("  skipped_already_resolved:  %d" % skipped_already_resolved)
    print("  skipped_error:             %d" % skipped_error)
    if error_reasons:
        print("  error reasons:")
        for reason in error_reasons:
            print("    - %s" % reason)
    print("-" * 70)
    if not apply_mode:
        print("This was a DRY RUN. Re-run with --apply to write changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
