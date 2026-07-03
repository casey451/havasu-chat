"""Targeted cleanup for 3 Parks & Rec rows with cross-contaminated descriptions.

The vision/flyer extraction of the LHC Parks & Rec monthly-calendar image bled a
neighboring "Free Summer Craft Series." sentence into two fishing events and
duplicated it into one craft row, and tagged the two fishing events `arts`.

Verified live (2026-06-28) — exactly three rows, by id:

  d0e40f6a  Strawberry Full Moon Fishing  2026-06-28  tags=['arts']
  01cd9a0f  Kids Fishing                  2026-06-28  tags=['family','arts','audience:youth']
  613de86b  Free Summer Craft Series      2026-06-29  tags=['arts']

Surgery (minimal, non-guessing — removes only foreign/duplicated content):
  * strip the bled/duplicated "Free Summer Craft Series." sentence from all 3
    descriptions (it is foreign to the two fishing rows and a self-duplicate in
    the craft row);
  * drop the wrong 'arts' tag from the two FISHING rows (fishing is not arts).

NOT touched (flagged for Casey — would be guessing):
  * Strawberry Full Moon Fishing date 2026-06-28 vs the reported "Strawberry
    Moon = June 29" — needs source-flyer verification, left as-is.
  * "For Ages 12 and up" on the craft row (craft siblings read "all ages") —
    likely bled from the fishing rows, but the true age is unknown; left as-is.

Dry-run by default. `--apply` writes (gated). Snapshots the before-state to a
JSON file for reversibility. READ-ONLY unless --apply is passed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db.database import SessionLocal
from app.db.models import Event

# The bled/duplicated sentence, exactly as it appears, with its leading space.
_BLED = " Free Summer Craft Series."

# id -> (expected current tags, cleaned tags). None = leave tags unchanged.
_TARGETS: dict[str, list[str] | None] = {
    "d0e40f6a-0a1d-4f68-be07-c8fae35b2a0a": [],  # Strawberry: drop 'arts'
    "01cd9a0f-7148-486f-a333-d107572dd9b8": ["family", "audience:youth"],  # Kids: drop 'arts'
    "613de86b-0843-4d6c-9b8a-5ef08f6dcb3b": None,  # Craft: tags ['arts'] correct, keep
}


def _clean_desc(desc: str) -> str:
    # Remove the bled sentence wherever it sits, collapse any doubled spaces.
    out = desc.replace(_BLED, "")
    while "  " in out:
        out = out.replace("  ", " ")
    return out.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (gated)")
    args = ap.parse_args()

    snapshot: list[dict] = []
    changed = 0
    with SessionLocal() as db:
        for ev_id, new_tags in _TARGETS.items():
            ev = db.query(Event).filter(Event.id == ev_id).one_or_none()
            if ev is None:
                print(f"!! {ev_id} NOT FOUND — skipping")
                continue
            old_desc = ev.description or ""
            new_desc = _clean_desc(old_desc)
            old_tags = list(ev.tags or [])
            tags_target = new_tags if new_tags is not None else old_tags

            desc_changed = new_desc != old_desc
            tags_changed = tags_target != old_tags
            if not (desc_changed or tags_changed):
                print(f"== {ev_id} {ev.title!r}: already clean, no change")
                continue

            changed += 1
            print("-" * 72)
            print(f"{ev.title!r}  ({ev.date})  id={ev_id}")
            if desc_changed:
                print(f"  desc OLD: {old_desc!r}")
                print(f"  desc NEW: {new_desc!r}")
            if tags_changed:
                print(f"  tags OLD: {old_tags!r}")
                print(f"  tags NEW: {tags_target!r}")

            snapshot.append(
                {
                    "id": ev_id,
                    "title": ev.title,
                    "old_description": old_desc,
                    "new_description": new_desc,
                    "old_tags": old_tags,
                    "new_tags": tags_target,
                }
            )

            if args.apply:
                ev.description = new_desc
                if tags_changed:
                    ev.tags = tags_target

        print("=" * 72)
        print(f"rows that would change: {changed}")

        if args.apply:
            snap_path = Path("scripts/_snapshots") / (
                "parks_rec_fishing_contamination_2026_06_28.json"
            )
            snap_path.parent.mkdir(parents=True, exist_ok=True)
            snap_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
            db.commit()
            print(f"APPLIED. snapshot -> {snap_path}")
        else:
            print("DRY-RUN (no writes). Re-run with --apply after approval.")


if __name__ == "__main__":
    main()
