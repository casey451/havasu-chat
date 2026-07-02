"""Backfill Lady Lee's Billiards Hall contact fields (2026-06-27).

Live prod audit (docs/ASKHAVA_DATA_FIXES_2026-06-27.md §1): the
``lady-lee-s-billiards-hall`` provider renders "Address not listed", no phone,
and "Hours not available" even though its own event rows already carry the
address. The venue's official site (ladyleesbilliards.com, fetched 2026-06-27)
and Yelp confirm:

    Address: 2180 McCulloch Blvd N, Lake Havasu City, AZ 86403
    Phone:   (928) 732-0426

ADDRESS + PHONE are unambiguous and are written every run (once --apply).

HOURS are a JUDGMENT CALL — the official site contradicts itself:
    "everyday"  -> "Everyday 11am-1am (kitchen closes 10pm)"   (Find Us block)
    "byday"     -> Mon-Thu 11a-10p / Fri-Sat 11a-12a / Sun 11a-9p  (footer)
Per CLAUDE.md we do NOT guess hours. Hours are written ONLY when an explicit
``--hours-variant {everyday,byday}`` is passed (Casey's pick, ideally confirmed
against the Google Business Profile). Without it, only address + phone change.

Read-only by default. ``--apply`` is a prod-data op: dry-run -> show counts ->
Casey approves -> apply (CLAUDE.md).

    .venv\\Scripts\\python.exe scripts\\backfill_lady_lees_2026_06_27.py            # DRY RUN (addr+phone)
    .venv\\Scripts\\python.exe scripts\\backfill_lady_lees_2026_06_27.py --hours-variant byday   # DRY RUN incl. hours
    .venv\\Scripts\\python.exe scripts\\backfill_lady_lees_2026_06_27.py --hours-variant byday --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

SLUG = "lady-lee-s-billiards-hall"
ADDRESS = "2180 McCulloch Blvd N, Lake Havasu City, AZ 86403"
PHONE = "(928) 732-0426"

HOURS_VARIANTS: dict[str, str] = {
    "everyday": "Open daily 11am-1am (kitchen closes 10pm)",
    "byday": "Mon-Thu 11am-10pm; Fri-Sat 11am-12am; Sun 11am-9pm",
}


def _target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Perform the writes (default: dry run).")
    ap.add_argument(
        "--hours-variant",
        choices=sorted(HOURS_VARIANTS),
        default=None,
        help="Which hours string to write (Casey's pick). Omit to leave hours untouched.",
    )
    args = ap.parse_args(argv)

    print(f"DB target: {_target()}\n")
    db = SessionLocal()
    try:
        p = db.query(Provider).filter(Provider.slug == SLUG).first()
        if p is None:
            print(f"ABORT: no provider with slug {SLUG!r}.")
            return 2

        new_hours = HOURS_VARIANTS[args.hours_variant] if args.hours_variant else None
        changes: list[tuple[str, object, object]] = []
        if (p.address or "").strip() != ADDRESS:
            changes.append(("address", p.address, ADDRESS))
        if (p.phone or "").strip() != PHONE:
            changes.append(("phone", p.phone, PHONE))
        if new_hours is not None and (p.hours or "").strip() != new_hours:
            changes.append(("hours", p.hours, new_hours))

        print(f"Provider {p.provider_name!r} (id={p.id})")
        if not changes:
            print("  nothing to change (already up to date).")
            return 0
        for field, old, new in changes:
            print(f"  {field:8}: {old!r}\n           -> {new!r}")
        if new_hours is None:
            print("\n  NOTE: hours left untouched (no --hours-variant). "
                  "Pass --hours-variant {everyday,byday} once Casey confirms.")

        if not args.apply:
            print(f"\nDRY RUN - would update {len(changes)} field(s). Re-run with --apply.")
            return 0

        for field, _old, new in changes:
            setattr(p, field, new)
        db.commit()
        print(f"\nAPPLIED - updated {len(changes)} field(s) on {SLUG}.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
