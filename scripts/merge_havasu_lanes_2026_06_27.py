"""Merge the duplicate Havasu Lanes provider rows into ONE + unify event labels.

Live prod audit (docs/ASKHAVA_DATA_FIXES_2026-06-27.md §2). The audit said "two
entities"; prod actually has FOUR Havasu-Lanes provider/entity rows for the one
bowling alley:

  slug                        active draft cat_id reviews  addr   source
  havasu-lanes                 yes    no    13     -        2128   go_lake_havasu   <- "Havasu Lanes" (Cosmic Bowling label)
  havasu-lanes-keglers-pub     yes    no    1      463      2134   google_places    <- complete Google record
  havasu-lanes-keglers-pub-2   yes    YES   23     -        2128   lhc_funzone      <- stray draft
  havasu-lanes-2               NO     no    15     -        2128   go_lake_havasu   <- already retired (left alone)

The bowling EVENTS all carry ``provider_id = NULL`` and attach to a venue page
purely by their ``location_name`` STRING:
  * "Cosmic Bowling" (16) + a few one-offs  -> location_name "Havasu Lanes"
  * daily "Bowling - Havasu Lanes & Keglers Pub" (7) -> "Havasu Lanes & Keglers Pub"
That split label is exactly why the reviewer saw "another place".

This script does TWO things:
  1. Folds every other ACTIVE havasu-lanes* provider into ``--keep-slug`` via the
     tested app.contrib.provider_merge.merge_providers primitive (gap-fills the
     keeper, repoints Event/Program/Claim/etc FKs, soft-retires losers with a
     301 ``merged_into_slug``). Folding the Google record gap-fills its 463
     reviews / rating / place_id onto the keeper.
  2. Relabels every Event whose ``location_name`` is a Havasu-Lanes variant to the
     single canonical display name (``--name``), so all bowling events read as one
     venue. (The events have no provider FK, so merge_providers can't reach them.)
  Optionally sets the keeper's display name (--name) on the provider + its entity.

JUDGMENT CALLS for Casey (do NOT apply until decided — CLAUDE.md):
  * --keep-slug   : which row survives. Recommended: ``havasu-lanes`` (clean slug;
                    folding the Google record gap-fills its reviews/place_id onto it).
  * --name        : canonical display name ("Havasu Lanes" vs "Havasu Lanes & Keglers Pub").
  * canonical ADDRESS (2128 alley vs 2134 pub) and CATEGORY (the row is currently
    spread across Eat & Drink / Fitness-Sports / Things-to-Do / Things-to-Do-&-
    Attractions) are NOT changed here — they touch Provider.category_id +
    EntityCategory + primary_category together and need Casey's bucket decision.

Read-only by default. ``--apply`` is a prod-data op: dry-run -> counts -> Casey
approves -> apply.

    .venv\\Scripts\\python.exe scripts\\merge_havasu_lanes_2026_06_27.py --keep-slug havasu-lanes --name "Havasu Lanes"
    .venv\\Scripts\\python.exe scripts\\merge_havasu_lanes_2026_06_27.py --keep-slug havasu-lanes --name "Havasu Lanes" --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contrib.provider_merge import merge_providers  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Entity, Event, Provider  # noqa: E402

# Event location_name strings (normalized) that denote this one venue. Used to
# relabel events to the canonical name. Kept explicit so we never touch an
# unrelated venue.
LANES_LOCATION_NORMS = {"havasu lanes", "havasu lanes & keglers pub"}


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keep-slug", required=True, help="Provider slug of the survivor.")
    ap.add_argument("--name", default=None, help="Canonical display name to set on keeper + its entity.")
    ap.add_argument("--apply", action="store_true", help="Perform the writes (default: dry run).")
    args = ap.parse_args(argv)

    print(f"DB target: {_target()}\n")
    db = SessionLocal()
    try:
        keep = db.query(Provider).filter(Provider.slug == args.keep_slug).first()
        if keep is None:
            print(f"ABORT: no provider with slug {args.keep_slug!r}.")
            return 2

        # Losers: every OTHER active havasu-lanes* provider (skip already-retired).
        losers = (
            db.query(Provider)
            .filter(Provider.slug.like("havasu-lanes%"))
            .filter(Provider.slug != args.keep_slug)
            .filter(Provider.is_active.is_(True))
            .all()
        )
        print(f"KEEP : {keep.slug!r} (id={keep.id}) name={keep.provider_name!r} "
              f"reviews={keep.google_review_count} place_id={bool(keep.google_place_id)}")
        print("FOLD :")
        for d in losers:
            print(f"   {d.slug!r} (id={d.id}) name={d.provider_name!r} src={d.source!r} "
                  f"reviews={d.google_review_count} draft={d.draft}")
        if not losers:
            print("   (none active to fold)")

        # 1. Merge each loser into the keeper (dry-run reports the blast radius).
        for d in losers:
            res = merge_providers(db, keep_id=keep.id, dup_id=d.id, dry_run=not args.apply)
            print(f"\n   merge {d.slug} -> {keep.slug}: gap_filled={res.gap_filled} "
                  f"repointed={res.repointed}")

        # 2. Relabel events to the canonical name (events carry no provider FK).
        canonical = (args.name or keep.provider_name or "").strip()
        relabel = [
            e for e in db.query(Event).all()
            if _norm(e.location_name) in LANES_LOCATION_NORMS and _norm(e.location_name) != _norm(canonical)
        ]
        from collections import Counter
        print(f"\nRELABEL events -> location_name {canonical!r} ({len(relabel)} rows):")
        for (t, loc), c in Counter((e.title, e.location_name) for e in relabel).most_common():
            print(f"   {c:>3}  {t[:38]!r:40} (was loc={loc!r})")

        # 3. Canonical display name on keeper + entity.
        name_changes: list[str] = []
        if args.name and keep.provider_name != args.name:
            name_changes.append(f"provider.provider_name {keep.provider_name!r} -> {args.name!r}")
        keep_ent = db.get(Entity, keep.entity_id)
        if args.name and keep_ent is not None and keep_ent.name != args.name:
            name_changes.append(f"entity.name {keep_ent.name!r} -> {args.name!r}")
        if name_changes:
            print("\nCANONICAL NAME:")
            for c in name_changes:
                print(f"   {c}")

        if not args.apply:
            print("\nDRY RUN - no writes. Re-run with --apply once Casey approves the keeper + name.")
            return 0

        # --- apply ---
        for e in relabel:
            e.location_name = canonical
            e.location_normalized = canonical.lower().strip()
        if args.name:
            keep.provider_name = args.name
            if keep_ent is not None:
                keep_ent.name = args.name
        db.commit()
        print(f"\nAPPLIED - folded {len(losers)} provider(s) into {keep.slug}, "
              f"relabeled {len(relabel)} event(s), name set to {canonical!r}.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
