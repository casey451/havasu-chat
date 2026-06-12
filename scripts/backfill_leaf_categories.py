"""Backfill existing entities onto the correct A.3 leaf (DRY-RUN by default; gated).

The forward fix (``app/contrib/leaf_type_mapping.py`` + ``places_load`` Layer 1.5,
2026-06-11) makes *new* scrapes auto-file onto the right leaf. This script applies
the same single-source mapping to the entities ALREADY in the DB — correcting the
historical leaf assignments that came from the one-time
``A-migration-PROD-final.csv`` whose divergent map produced the reported misfiles.

For every active Provider it derives the canonical leaf from the provider's Google
types (``google_primary_category`` first, then ``google_categories``) via
``map_google_types_to_leaf_slug``:

* **reassign** — the derived leaf is a real seeded leaf AND differs from the
  entity's current PRIMARY ``entity_categories`` link → stage a primary swap
  (clear the old primary, set the leaf primary). Same write shape as
  ``apply_taxonomy_remap``.
* **non_directory** — the provider's types are a calendar-event venue
  (``event_venue`` …). NOT touched here (reassigning would just move it to
  another directory leaf); these are handled by the event-misfile EXCLUDE flow.
  Reported only.
* **unchanged / unmapped** — primary already correct, or no confident leaf
  (kept on its existing assignment; never guessed away).

Protections: skips entities with a verified ``Claim`` (operator-curated) so a
human-corrected assignment is never auto-reverted. Reassigns only when the target
leaf exists in this DB.

DEFAULT IS DRY-RUN: prints the action plan + a sample, writes nothing. ``--apply``
requires ``--confirm``, wraps writes in ONE transaction, and first saves a
rollback snapshot of every touched ``entity_categories`` row. Every run prints the
sanitized DB target (the repo's .env can point DATABASE_URL at prod).

    .venv\\Scripts\\python.exe scripts\\backfill_leaf_categories.py                    # DRY RUN
    .venv\\Scripts\\python.exe scripts\\backfill_leaf_categories.py --csv plan.csv     # DRY RUN + CSV
    .venv\\Scripts\\python.exe scripts\\backfill_leaf_categories.py --apply --confirm  # writes

PROD GATE (CLAUDE.md): run dry, show Casey the counts, get approval, THEN a human
runs --apply --confirm against prod. The agent never runs --apply against prod.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.contrib.leaf_type_mapping import map_google_types_to_leaf_slug  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, Claim, Entity, EntityCategory, Provider  # noqa: E402


def provider_types(google_primary_category: str | None, google_categories=None) -> list[str]:
    """Authoritative PRIMARY type for leaf resolution (primary only).

    The noisy secondary ``google_categories`` array is intentionally ignored:
    matching its tokens produced wrong reassignments (the 2026-06-12 backfill
    incident — Dillard's → shoes via a ``shoe_store`` secondary). When the
    primary type is absent the provider stays unmapped (its existing leaf is
    kept) rather than guessing from a secondary token. ``google_categories`` is
    accepted for call-site compatibility but unused."""
    return [str(google_primary_category)] if google_primary_category else []


def target_leaf(google_primary_category: str | None, google_categories) -> tuple[str | None, bool]:
    """``(leaf_slug, non_directory)`` for a provider — pure, no DB."""
    return map_google_types_to_leaf_slug(
        provider_types(google_primary_category, google_categories)
    )


# Generic Google "umbrella" primary types — a business carries one when Google
# has no specific primary (a handyman is ``service``, a wholesaler ``supplier``,
# a strip-mall shop ``store``). These must NEVER drive a leaf reassignment. The
# resolver already leaves them unmapped, so this is a belt-and-suspenders guard:
# even if one were ever (mis)added to ``_TYPE_TO_LEAF``, the backfill refuses to
# act on it and reports it separately — so a generic primary can never slip into
# a reassignment via a dry-run (2026-06-12 incident hardening).
GENERIC_PRIMARY_TYPES: frozenset[str] = frozenset(
    {
        "service",
        "supplier",
        "store",
        "consultant",
        "establishment",
        "point_of_interest",
    }
)


def is_generic_primary(google_primary_category: str | None) -> bool:
    """True if the provider's PRIMARY google type is a generic umbrella token
    that must never produce a leaf reassignment — pure, no DB."""
    return (google_primary_category or "").strip().lower() in GENERIC_PRIMARY_TYPES


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def run(
    *,
    apply: bool = False,
    confirm: bool = False,
    csv_path: Path | None = None,
    snapshot_dir: Path | None = None,
    session=None,
) -> Counter:
    """Stage (and optionally commit) the leaf backfill. Dry-run by default."""
    snapshot_dir = snapshot_dir or _ROOT
    own_session = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    try:
        print(f"DB target: {_sanitized_target()}\n")

        leaf_id_by_slug: dict[str, int] = {
            c.slug: c.id
            for c in session.query(Category).filter(Category.level == 1).all()
        }
        claimed = {
            eid
            for (eid,) in session.query(Claim.entity_id).filter(
                Claim.status == "verified"
            )
        }
        current_primary = {
            ec.entity_id: ec.category_id
            for ec in session.query(EntityCategory).filter(
                EntityCategory.is_primary.is_(True)
            )
        }

        providers = (
            session.query(Provider)
            .join(Entity, Provider.entity_id == Entity.id)
            .filter(Entity.is_active.is_(True), Provider.is_active.is_(True))
            .all()
        )
        counts["providers_scanned"] = len(providers)

        staged: list[tuple[str, int, str]] = []  # (entity_id, new_leaf_id, leaf_slug)
        report_rows: list[dict] = []
        generic_rows: list[dict] = []
        for p in providers:
            eid = p.entity_id
            if eid is None:
                continue
            # Hard guard: a generic umbrella primary can never be reassigned,
            # independent of the resolver. Reported separately, never staged.
            if is_generic_primary(p.google_primary_category):
                counts["generic_primary_skipped"] += 1
                generic_rows.append(
                    {
                        "entity_id": eid,
                        "provider_name": (p.provider_name or "").strip(),
                        "google_primary_category": p.google_primary_category or "",
                    }
                )
                continue
            leaf_slug, non_directory = target_leaf(
                p.google_primary_category, p.google_categories
            )
            if non_directory:
                counts["non_directory_skipped"] += 1
                continue
            if leaf_slug is None:
                counts["unmapped"] += 1
                continue
            new_id = leaf_id_by_slug.get(leaf_slug)
            if new_id is None:
                counts["leaf_absent_in_db"] += 1
                continue
            if current_primary.get(eid) == new_id:
                counts["unchanged"] += 1
                continue
            if eid in claimed:
                counts["protected_claimed"] += 1
                continue
            counts["would_reassign"] += 1
            staged.append((eid, new_id, leaf_slug))
            report_rows.append(
                {
                    "entity_id": eid,
                    "provider_name": (p.provider_name or "").strip(),
                    "google_primary_category": p.google_primary_category or "",
                    "current_primary_category_id": current_primary.get(eid) or "",
                    "new_leaf_slug": leaf_slug,
                    "new_leaf_category_id": new_id,
                }
            )

        # ---- report ----
        print("backfill plan:")
        for k in (
            "would_reassign",
            "unchanged",
            "unmapped",
            "generic_primary_skipped",
            "non_directory_skipped",
            "protected_claimed",
            "leaf_absent_in_db",
        ):
            print(f"  {counts.get(k, 0):>6}  {k}")
        print(f"  {counts['providers_scanned']:>6}  providers_scanned\n")

        for r in report_rows[:25]:
            print(
                f"  {r['provider_name'][:36]:36s} | {r['google_primary_category'][:20]:20s}"
                f" -> {r['new_leaf_slug']}"
            )

        if generic_rows:
            print(
                f"\ngeneric-primary providers skipped (never reassigned) — "
                f"showing {min(len(generic_rows), 25)} of {len(generic_rows)}:"
            )
            for r in generic_rows[:25]:
                print(
                    f"  {r['provider_name'][:36]:36s} | "
                    f"{r['google_primary_category'][:20]:20s} -> (skipped: generic primary)"
                )

        if csv_path and report_rows:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(report_rows[0].keys()))
                w.writeheader()
                w.writerows(report_rows)
            print(f"\nwrote {len(report_rows)} planned reassignments to {csv_path}")

        if not apply:
            print(
                "\nDRY RUN — no rows written. Re-run with --apply --confirm to write."
            )
            return counts
        if not confirm:
            print(
                f"\nREFUSING TO WRITE — --apply requires --confirm. Target is "
                f"{_sanitized_target()}."
            )
            return counts

        # ---- rollback snapshot ----
        touched = list({eid for eid, _, _ in staged})
        snapshot = [
            {
                "id": ec.id,
                "entity_id": ec.entity_id,
                "category_id": ec.category_id,
                "is_primary": ec.is_primary,
            }
            for ec in session.query(EntityCategory).filter(
                EntityCategory.entity_id.in_(touched)
            )
        ] if touched else []
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap_path = snapshot_dir / f"leaf_backfill_snapshot_{stamp}.json"
        snap_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        print(f"\nrollback snapshot: {snap_path} ({len(snapshot)} rows)")

        # ---- one transaction: swap primaries ----
        for entity_id, new_leaf_id, _slug in staged:
            for ec in session.query(EntityCategory).filter(
                EntityCategory.entity_id == entity_id,
                EntityCategory.is_primary.is_(True),
            ):
                ec.is_primary = False
            existing = session.query(EntityCategory).filter(
                EntityCategory.entity_id == entity_id,
                EntityCategory.category_id == new_leaf_id,
            ).one_or_none()
            if existing is None:
                session.add(
                    EntityCategory(
                        entity_id=entity_id,
                        category_id=new_leaf_id,
                        is_primary=True,
                    )
                )
            else:
                existing.is_primary = True
        session.commit()
        counts["primaries_changed"] = len(staged)
        print(f"\nAPPLIED — {len(staged)} primary reassignments in one transaction.")
        return counts
    finally:
        if own_session:
            session.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Backfill entities onto the correct A.3 leaf.")
    ap.add_argument("--apply", action="store_true", help="Write (default: dry-run).")
    ap.add_argument("--confirm", action="store_true", help="Required with --apply.")
    ap.add_argument("--csv", type=Path, default=None, help="Write the planned reassignments to this CSV.")
    args = ap.parse_args(argv)
    run(apply=args.apply, confirm=args.confirm, csv_path=args.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
