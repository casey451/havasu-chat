"""
Phase 5 — repoint event ``event_url`` from scrape/aggregator links to the venue's
primary source (own site → Facebook). Mapping derived from
``relay/ASK_HAVA_PHASE5_EVENT_LINK_AUDIT_2026-06-17.md``.

  python scripts/phase5_event_link_repoint.py            # preview (default)
  python scripts/phase5_event_link_repoint.py --dry-run  # explicit preview
  python scripts/phase5_event_link_repoint.py --apply    # persist + write undo snapshot

Matching is by EXACT current ``event_url`` (trailing slash ignored), so the script
only ever touches a row whose outbound link is still the known scrape URL — an
already-fixed or expired event simply reports ``no_match`` and is skipped.

On ``--apply`` each matched row gets ``event_url`` set to the primary URL, and —
to preserve provenance and light up the detail page's new "Source:" byline — its
``source_url`` is set to the OLD scrape URL *only when ``source_url`` is empty*
(an existing source_url is never clobbered). An undo snapshot (id + old
event_url/source_url) is written to ``relay/`` before any commit.

Counter partition: ``len(REPOINTS) == needs_url + no_match + already_ok + would_change``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Event


@dataclass(frozen=True)
class Repoint:
    """One repoint rule: match the row by its current ``event_url``."""

    match: str  # current (scrape/aggregator) event_url
    to: str | None  # primary URL to set; None => unresolved, skip (needs Casey)
    venue: str  # human label for the preview


# Lighthouse Lounge has no standalone website -> its Facebook page is the primary.
_LIGHTHOUSE_FB = "https://www.facebook.com/profile.php?id=61550826508124"
_AQUATIC = "https://www.lhcaz.gov/parks-recreation/aquatic-center"

REPOINTS: list[Repoint] = [
    # riverscenemagazine.com (scrape source) -> Star Cinemas own site
    Repoint(
        "https://riverscenemagazine.com/events/summer-free-movies-sonic-the-hedgehog-3-star-cinemas-3/",
        "https://starcinemashavasu.com/",
        "Star Cinemas",
    ),
    Repoint(
        "https://riverscenemagazine.com/events/summer-free-movies-if-star-cinemas/",
        "https://starcinemashavasu.com/",
        "Star Cinemas",
    ),
    # golakehavasu.com (tourism aggregator) -> the venue
    Repoint(
        "https://www.golakehavasu.com/events/wine-watercolor-with-kj/",
        "https://summeraywinebar.com/",
        "SummeRay Wine Bar",
    ),
    Repoint(
        "https://www.golakehavasu.com/events/sippin-with-the-somm1/",
        "https://foundryhavasu.com/",
        "The Foundry Plates & Spirits",
    ),
    Repoint(
        "https://www.golakehavasu.com/events/hav-a-sis-game-night/",
        "https://havasis.org/",
        "Hav-A-Sis (Grapes N Grains)",
    ),
    Repoint(
        "https://www.golakehavasu.com/events/america-250-celebration-pizza-pool-party/",
        _AQUATIC,
        "Aquatic Center (city)",
    ),
    Repoint(
        "https://www.golakehavasu.com/events/wine-tasting/",
        "https://www.theviewsatlakehavasu.com/",
        "The Views at Lake Havasu",
    ),
    # allevents.in (aggregator) -> venue resolved from the listing's own data
    Repoint(
        "https://allevents.in/lake-havasu-city/the-brew-band/200030132717746",
        _LIGHTHOUSE_FB,
        "Lighthouse Lounge",
    ),
    Repoint(
        "https://allevents.in/lake-havasu-city/a-z/200030130283746",
        _LIGHTHOUSE_FB,
        "Lighthouse Lounge",
    ),
    Repoint(
        "https://allevents.in/lake-havasu-city/motor-madness-cruise-in-event/200030157018337",
        _LIGHTHOUSE_FB,
        "Lighthouse Lounge",
    ),
    Repoint(
        "https://allevents.in/lake-havasu-city/jonnys-open-mic-bingo/200030157017936",
        _LIGHTHOUSE_FB,
        "Lighthouse Lounge",
    ),
    Repoint(
        "https://allevents.in/lake-havasu-city/sparks-after-midnight/200030130285753",
        _LIGHTHOUSE_FB,
        "Lighthouse Lounge",
    ),
    Repoint(
        "https://allevents.in/lake-havasu-city/sacred-stone/200030130285853",
        _LIGHTHOUSE_FB,
        "Lighthouse Lounge",
    ),
    Repoint(
        "https://allevents.in/lake-havasu-city/harleyz-and-hot-rodz-bike-night/200030186746330",
        "https://www.facebook.com/harleyzandhotrodz/",
        "Harleyz & Hot Rodz Motor Pub and Grill",
    ),
    Repoint(
        "https://allevents.in/lake-havasu-city/open-swim/200030183100650",
        _AQUATIC,
        "Aquatic Center (city)",
    ),
]


def _norm(url: str | None) -> str:
    return (url or "").strip().rstrip("/")


def _match_events(db: Session, match_url: str) -> list[Event]:
    """Live events whose current event_url equals ``match_url`` (slash-insensitive)."""
    target = _norm(match_url)
    rows = db.execute(select(Event).where(Event.status == "live")).scalars().all()
    return [ev for ev in rows if _norm(ev.event_url) == target]


def repoint_events(db: Session, *, apply: bool, snapshot_dir: Path | None = None) -> Counter[str]:
    """Preview (or apply) the Phase 5 repoints. Returns a counter of outcomes.

    On ``apply``, an undo snapshot is written under ``snapshot_dir`` (default:
    the repo's ``relay/``) before the commit.
    """
    c: Counter[str] = Counter()
    undo: list[dict[str, str | None]] = []

    for rp in REPOINTS:
        c["total"] += 1
        if rp.to is None:
            c["needs_url"] += 1
            print(f"--- SKIP (needs URL): {rp.venue}\n      {rp.match}")
            continue

        matched = _match_events(db, rp.match)
        if not matched:
            c["no_match"] += 1
            print(f"--- no_match: {rp.venue}\n      {rp.match}")
            continue

        # Entry-level partition: an entry is "already_ok" only when every matched
        # row already points at the target; otherwise it counts as one change.
        changed = [ev for ev in matched if _norm(ev.event_url) != _norm(rp.to)]
        if not changed:
            c["already_ok"] += 1
            continue
        c["would_change"] += 1

        for ev in changed:
            c["events_changed"] += 1
            print(f"--- event {ev.id}  ({rp.venue})")
            print(f"  event_url:  {ev.event_url!r}")
            print(f"         ->   {rp.to!r}")
            keep_source = (ev.source_url or "").strip()
            new_source = keep_source or ev.event_url  # preserve provenance for the byline
            if not keep_source:
                print(f"  source_url: {ev.source_url!r}  ->  {new_source!r}  (provenance)")
            if apply:
                undo.append(
                    {"id": ev.id, "event_url": ev.event_url, "source_url": ev.source_url}
                )
                ev.event_url = rp.to
                if not keep_source:
                    ev.source_url = new_source
                db.add(ev)

    if apply and undo:
        out_dir = snapshot_dir or (Path(__file__).resolve().parents[1] / "relay")
        out_dir.mkdir(parents=True, exist_ok=True)
        snap = out_dir / f"_phase5_repoint_undo_{datetime.now():%Y%m%dT%H%M%S}.json"
        snap.write_text(json.dumps(undo, indent=2), encoding="utf-8")
        db.commit()
        c["applied"] = len(undo)
        print(f"\ninfo: applied {len(undo)} repoints; undo snapshot -> {snap}")

    print("\nPhase 5 event-link repoint complete")
    for k in ("total", "needs_url", "no_match", "already_ok", "would_change",
              "events_changed", "applied"):
        print(f"  {k:15} {c[k]}")

    partition = c["needs_url"] + c["no_match"] + c["already_ok"] + c["would_change"]
    if partition != c["total"]:
        raise RuntimeError(f"counter partition broken: {partition} != total {c['total']}")
    if not apply:
        assert c["applied"] == 0, f"dry-run must not persist (applied={c['applied']})"
    else:
        assert c["applied"] == c["events_changed"], (
            f"applied ({c['applied']}) != events_changed ({c['events_changed']})"
        )
    return c


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=False)
    mode.add_argument(
        "--dry-run", action="store_true", help="Preview without writing (default)."
    )
    mode.add_argument("--apply", action="store_true", help="Persist updates + undo snapshot.")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    with SessionLocal() as db:
        repoint_events(db, apply=bool(args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
