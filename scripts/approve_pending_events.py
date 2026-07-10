"""Approve specific PENDING event contributions into the live catalog (WS12).

The review-queue gate: a connector files events as PENDING contributions
(training wheels); this publishes the ones a human has approved, by id. There is
no batch-approve in /admin (only per-id forms), so this is the id-scoped path.
Gated: dry-run by default, --apply writes; wrap in a production-writes workflow
with a confirm phrase.

Field mapping mirrors scripts/approve_pending_river_scene.py (venue from a
'Venue:' notes line; description = notes, which approve_contribution_as_event
sanitises). Tags: for youth-fixture rows we recover the exact fixture tags from
the '?occ=<slug>-<date>' URL so an approved row matches its already-live
siblings; otherwise a 'Categories:' notes line, else none.

Usage:
    python scripts/approve_pending_events.py --ids "2371 2372"          # dry-run
    python scripts/approve_pending_events.py --ids "2371,2372" --apply  # writes
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.contrib.approval_service import approve_contribution_as_event  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Contribution  # noqa: E402
from app.schemas.contribution import EventApprovalFields  # noqa: E402

_DEFAULT_VENUE = "Lake Havasu"
_OCC_RE = re.compile(r"[?&]occ=([^&]+)")


def _venue_from_notes(notes: str | None) -> str:
    for raw in (notes or "").splitlines():
        line = raw.strip()
        if line.lower().startswith("venue:"):
            rest = line[6:].strip()
            return rest if len(rest) >= 3 else _DEFAULT_VENUE
    return _DEFAULT_VENUE


def _tags_from_notes(notes: str | None) -> list[str]:
    for raw in (notes or "").splitlines():
        line = raw.strip()
        if line.lower().startswith("categories:"):
            return [p.strip() for p in line[11:].split(",") if p.strip()]
    return []


def _youth_fixture_tags(url: str | None) -> list[str] | None:
    """Recover havasu_youth fixture tags from a '?occ=<slug>-<YYYY-MM-DD>' URL."""
    if not url:
        return None
    m = _OCC_RE.search(url)
    if not m:
        return None
    slug = m.group(1).rsplit("-", 3)[0]  # strip the trailing -YYYY-MM-DD
    try:
        from app.events.scrapers.havasu_youth import _BY_SLUG
    except Exception:
        return None
    fx = _BY_SLUG.get(slug)
    return list(fx.tags) if fx else None


def _tags_for(c: Contribution) -> list[str]:
    return (
        _youth_fixture_tags(c.submission_url)
        or _youth_fixture_tags(c.source_url)
        or _tags_from_notes(c.submission_notes)
    )


def _fields_from_contribution(c: Contribution) -> tuple[EventApprovalFields, list[str]]:
    url = (c.submission_url or "").strip()
    if not url:
        raise ValueError("submission_url is required for event approval")
    if c.event_date is None or c.event_time_start is None:
        raise ValueError("event_date and event_time_start are required")
    notes = c.submission_notes or ""
    fields = EventApprovalFields(
        title=c.submission_name,
        description=notes,
        date=c.event_date,
        end_date=c.event_end_date,
        start_time=c.event_time_start,
        end_time=c.event_time_end,
        location_name=_venue_from_notes(notes),
        event_url=url,
    )
    return fields, _tags_for(c)


def _parse_ids(raw: list[str]) -> list[int]:
    out: list[int] = []
    for chunk in raw:
        for tok in re.split(r"[,\s]+", chunk.strip()):
            if tok:
                out.append(int(tok))
    return out


def run(ids: list[int], *, apply: bool) -> int:
    approved = failed = skipped = 0
    with SessionLocal() as db:
        for cid in ids:
            c = db.get(Contribution, cid)
            if c is None:
                print(f"skip {cid}: not found", file=sys.stderr)
                skipped += 1
                continue
            if c.status != "pending" or c.entity_type != "event":
                print(f"skip {cid}: status={c.status} type={c.entity_type} (idempotent)")
                skipped += 1
                continue
            try:
                fields, tags = _fields_from_contribution(c)
            except Exception as e:
                print(f"error {cid}: {e}", file=sys.stderr)
                failed += 1
                continue
            print(
                f"{'APPLY' if apply else 'DRY '} {cid}: {fields.title!r} "
                f"{fields.date} {fields.start_time} @ {fields.location_name} tags={tags}"
            )
            if not apply:
                continue
            try:
                ev = approve_contribution_as_event(db, c.id, fields, tags)
                print(f"  -> published event {ev.id}")
                approved += 1
            except Exception as e:
                print(f"error {cid}: {e}", file=sys.stderr)
                failed += 1

    print(f"\n{'APPLIED' if apply else 'DRY-RUN'}: approved={approved} "
          f"skipped={skipped} failed={failed} of {len(ids)}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Approve pending event contributions by id")
    ap.add_argument("--ids", action="append", required=True, help="space/comma-separated ids")
    ap.add_argument("--apply", action="store_true", help="write (default: dry-run)")
    args = ap.parse_args(argv)
    ids = _parse_ids(args.ids)
    if not ids:
        ap.error("no ids provided")
    return run(ids, apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
