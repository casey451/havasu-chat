"""Toggle the editorial ``featured: bool`` flag on a catalog row.

BUILD.md step 8 — surfacing the toggle in ``/admin`` is deferred. Until
that lands, flip the flag from the command line.

USAGE
-----

  # Set featured=True
  python -m scripts.toggle_featured event   <event_id>     on
  python -m scripts.toggle_featured program <program_id>   on
  python -m scripts.toggle_featured provider <provider_id> on

  # Clear it
  python -m scripts.toggle_featured event <event_id> off

  # List currently featured rows in a table
  python -m scripts.toggle_featured list

  # Find candidates by name match (helps locate the id)
  python -m scripts.toggle_featured find "channel brewing"

DESIGN NOTES
------------

* Rules of thumb live in BUILD.md "Hava's pick" badges. One pick per
  row on the home page (Tonight / This week / New on Hava). The home
  query layer caps at one per row already; setting more than one flag
  in a row's source set just means the most-recently-created wins.

* Distinct from spotlight monetization. ``featured`` is editorial; paid
  placement uses ``Provider.tier`` + ``sponsored_until``. Don't conflate.

* No /admin UI yet by design — this script keeps the flag-flipping
  ergonomic for hand curation while we let the rest of the build settle.
"""

from __future__ import annotations

import argparse
import sys
from typing import Type

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Event, Program, Provider

_TABLES: dict[str, tuple[Type, str]] = {
    "event": (Event, "title"),
    "program": (Program, "title"),
    "provider": (Provider, "provider_name"),
}


def _set_flag(db: Session, kind: str, row_id: str, value: bool) -> int:
    Model, name_field = _TABLES[kind]
    row = db.get(Model, row_id)
    if row is None:
        print(f"!! no {kind} with id={row_id}")
        return 1
    before = row.featured
    row.featured = value
    db.commit()
    print(f"{kind} {row_id} ({getattr(row, name_field)!r}): featured {before} -> {value}")
    return 0


def _list_featured(db: Session) -> int:
    print("FEATURED rows (editorial picks)")
    print("-" * 64)
    any_found = False
    for kind, (Model, name_field) in _TABLES.items():
        rows = db.query(Model).filter(Model.featured.is_(True)).all()
        for r in rows:
            any_found = True
            print(f"  [{kind:8}] {r.id}  {getattr(r, name_field)!r}")
    if not any_found:
        print("  (none — nothing is featured right now)")
    return 0


def _find(db: Session, query: str) -> int:
    needle = (query or "").strip().lower()
    if not needle:
        print("!! empty query")
        return 1
    print(f"matches for {query!r}")
    print("-" * 64)
    any_found = False
    for kind, (Model, name_field) in _TABLES.items():
        col = getattr(Model, name_field)
        rows = db.query(Model).filter(col.ilike(f"%{needle}%")).limit(20).all()
        for r in rows:
            any_found = True
            featured_marker = "★" if r.featured else " "
            print(f"  {featured_marker} [{kind:8}] {r.id}  {getattr(r, name_field)!r}")
    if not any_found:
        print("  (no matches)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Toggle the editorial featured flag.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    on_off = sub.add_parser("on", help=argparse.SUPPRESS)
    on_off  # placeholder; the actual subcommands are below

    for cmd in ("on", "off"):
        p = sub.add_parser(cmd, help=f"set featured={cmd == 'on'} on a row")
        p.add_argument("kind", choices=sorted(_TABLES.keys()))
        p.add_argument("row_id")

    sub.add_parser("list", help="list all currently-featured rows")

    p_find = sub.add_parser("find", help="search rows by name substring")
    p_find.add_argument("query")

    # Backward-compat: `toggle_featured event <id> on`
    # If first arg is a kind, transparently rewrite to `on` / `off` form.
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] in _TABLES and len(argv) >= 3 and argv[2] in ("on", "off"):
        argv = [argv[2], argv[0], argv[1]] + argv[3:]

    args = parser.parse_args(argv)

    with SessionLocal() as db:
        if args.cmd in ("on", "off"):
            return _set_flag(db, args.kind, args.row_id, args.cmd == "on")
        if args.cmd == "list":
            return _list_featured(db)
        if args.cmd == "find":
            return _find(db, args.query)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
