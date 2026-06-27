"""Publish the captured strength-gym class schedules onto the calendar (2026-06-27).

scripts/import_captured_schedules.py created the Havasu CrossFit / Fit Lab 928 /
Feelin' Good Fitness class rows as PENDING ``schedule_scrape`` program
contributions (autopublish is off by default). Casey: "all gym programs and
classes we have the right info on need to be in the calendar." This publishes
exactly those three gyms' pending rows via the tested
app.contrib.schedule_publish.publish_contribution primitive — which attaches a
recurring Schedule + Offering to the EXISTING venue entity (idempotent; never
mints a duplicate venue). Published rows then render under Fitness & Sports ->
Strength & Cardio.

Scoped to an ALLOWLIST of venue entity ids so nothing else in the pending queue
is touched. Deliberately EXCLUDES Fiore's Endorphin Factory (its live schedule
currently shows no sessions — we do NOT have the right info; it stays pending).

Read-only by default. ``--apply`` is a prod-data op: dry-run -> counts -> Casey
approves -> apply (CLAUDE.md).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contrib.schedule_publish import publish_contribution  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Contribution, Entity  # noqa: E402

# The three confirmed strength gyms (pinned entity ids from the dataset).
GYM_ENTITY_IDS: dict[str, str] = {
    "a08914b6-f3d8-4046-bf79-327d050f06a8": "Havasu CrossFit",
    "70ee0292-abdc-4796-9f76-be9879e6579f": "Fit Lab 928",
    "6caa04c2-e6d1-4567-963f-a25e4f3c05a0": "Feelin' Good Fitness",
}


def _target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Publish (default: dry run).")
    args = ap.parse_args(argv)

    print(f"DB target: {_target()}\n")
    db = SessionLocal()
    try:
        pending = (
            db.query(Contribution)
            .filter(
                Contribution.source == "schedule_scrape",
                Contribution.status == "pending",
                Contribution.target_entity_id.in_(list(GYM_ENTITY_IDS)),
            )
            .order_by(Contribution.target_entity_id, Contribution.submission_name)
            .all()
        )
        # Safety: confirm every target entity still exists + is active.
        for eid, name in GYM_ENTITY_IDS.items():
            ent = db.get(Entity, eid)
            if ent is None or not ent.is_active:
                print(f"ABORT: gym entity {name} ({eid}) missing or inactive.")
                return 2

        from collections import Counter
        by_gym = Counter(GYM_ENTITY_IDS.get(c.target_entity_id, "?") for c in pending)
        print(f"PENDING schedule_scrape rows for the 3 gyms ({len(pending)}):")
        for gym, n in by_gym.most_common():
            print(f"  {n:>3}  {gym}")
        for c in pending:
            print(f"    [{GYM_ENTITY_IDS.get(c.target_entity_id,'?')[:14]:14}] {c.submission_name}")

        if not pending:
            print("\nNothing pending — already published or none imported.")
            return 0

        if not args.apply:
            print(f"\nDRY RUN - would publish {len(pending)} contribution(s). Re-run with --apply.")
            return 0

        published = 0
        skipped: Counter = Counter()
        for c in pending:
            res = publish_contribution(db, c)
            if res.get("status") == "published":
                published += 1
            else:
                skipped[res.get("reason", "?")] += 1
        print(f"\nAPPLIED - published {published} / {len(pending)}; skipped={dict(skipped)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
