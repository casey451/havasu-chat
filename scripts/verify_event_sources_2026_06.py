"""P2 source-verification sweep — every live event must resolve to a verifiable
external source, or be removed.

Read-only by default (``--dry-run``). The actual writes (retire a sourceless
event, swap in a real source, clear a wrong-target byline) are a PROD-DB op and
stay behind ``--apply`` per CLAUDE.md: dry-run -> show counts -> Casey approves ->
apply. An undo snapshot is written before any commit.

Buckets (the rendered PRIMARY link is ``event_url or source_url``):
- OK             — primary is a verifiable external URL.
- WEAK_OK        — primary resolves but is a generic venue FB *profile*
                   (facebook.com/profile.php — the Lighthouse pattern). Reported,
                   never auto-changed; a human decides.
- RESOURCE       — primary is a self-link but the OTHER field is a real external
                   URL → swap it into ``event_url``.
- RELABEL_SOURCE — primary is fine but ``source_url`` is a known wrong-target
                   byline (the Clifford/SpongeBob → Sonic mislabels) → clear it.
- REMOVE         — no verifiable source in either field → retire (status=deleted,
                   i.e. 410, never a hard delete).

Note: the P1 ``#program-*`` self-anchors are RENDER-TIME ids on recurring Schedule
occurrences (app.events.class_occurrences.program_anchor) — they are NOT stored on
any Event row, so this events sweep does not touch them (they need a real provider
page or stay link-less; separate concern).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import Event
from app.events.description_clean import valid_event_url

# Known wrong-target source_url bylines (P1 finding 21): a movie record citing a
# DIFFERENT movie's RiverScene URL. Substring match on the (lowercased) title;
# action = clear the misleading source_url (the event_url primary is already the
# correct Star Cinemas page).
WRONG_SOURCE_TITLE_HINTS: tuple[str, ...] = ("clifford", "spongebob")
_WRONG_SOURCE_URL_HINT = "sonic"

OK, WEAK_OK, RESOURCE, RELABEL_SOURCE, REMOVE = (
    "OK", "WEAK_OK", "RESOURCE", "RELABEL_SOURCE", "REMOVE"
)
_BUCKETS = (OK, WEAK_OK, RESOURCE, RELABEL_SOURCE, REMOVE)


def classify_event_source(event_url: str | None, source_url: str | None, title: str = "") -> str:
    """Bucket a live event by the verifiability of its rendered primary link."""
    eu = (event_url or "").strip()
    su = (source_url or "").strip()
    primary = eu or su
    if not primary:
        return REMOVE
    if valid_event_url(primary):
        # A real external link that happens to be the wrong-target byline case.
        low_t = title.lower()
        if (
            su
            and _WRONG_SOURCE_URL_HINT in su.lower()
            and any(h in low_t for h in WRONG_SOURCE_TITLE_HINTS)
        ):
            return RELABEL_SOURCE
        if "facebook.com/profile.php" in primary.lower():
            return WEAK_OK
        return OK
    # Primary is a self-link / dead / internal. Is the OTHER field a real source?
    other = su if primary == eu else eu
    if valid_event_url(other):
        return RESOURCE
    return REMOVE


def main() -> int:
    ap = argparse.ArgumentParser(description="P2 event source-verification sweep")
    ap.add_argument("--apply", action="store_true", help="commit changes (default: dry-run)")
    args = ap.parse_args()
    apply = bool(args.apply)

    db = SessionLocal()
    applied = 0
    snapshot: list[dict] = []
    try:
        rows = db.execute(select(Event).where(Event.status == "live")).scalars().all()
        counts: Counter[str] = Counter()
        previews: dict[str, list[str]] = {b: [] for b in _BUCKETS}
        for ev in rows:
            bucket = classify_event_source(ev.event_url, ev.source_url, ev.title or "")
            counts[bucket] += 1
            if bucket != OK:
                previews[bucket].append(
                    f"  [{bucket}] {ev.id} | {ev.title!r}\n"
                    f"        event_url={ev.event_url!r}\n        source_url={ev.source_url!r}"
                )
            if not apply or bucket in (OK, WEAK_OK):
                continue
            snapshot.append(
                {"id": ev.id, "event_url": ev.event_url, "source_url": ev.source_url,
                 "status": ev.status, "bucket": bucket}
            )
            if bucket == REMOVE:
                ev.status = "deleted"
            elif bucket == RESOURCE:
                ev.event_url = (
                    valid_event_url(ev.source_url) or valid_event_url(ev.event_url) or ev.event_url
                )
            elif bucket == RELABEL_SOURCE:
                ev.source_url = None
            applied += 1

        total = sum(counts.values())
        assert total == len(rows), (total, len(rows))
        print(f"live events: {len(rows)}")
        for b in _BUCKETS:
            print(f"  {b:14} {counts[b]}")
        for b in (REMOVE, RESOURCE, RELABEL_SOURCE, WEAK_OK):
            if previews[b]:
                print(f"\n--- {b} ({counts[b]}) ---")
                print("\n".join(previews[b]))

        if apply:
            snap_path = Path("relay") / "verify_event_sources_2026_06_undo.json"
            snap_path.parent.mkdir(parents=True, exist_ok=True)
            snap_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
            db.commit()
            print(f"\nAPPLIED {applied} change(s); undo snapshot -> {snap_path}")
        else:
            assert applied == 0
            print("\nDRY-RUN — no writes. Re-run with --apply after approval.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
