"""Soft-delete synthetic test/seed fixtures that leak into the live catalog.

A handful of pytest/seed fixtures (``Acme Plumbing``, ``… Test Fixture``,
``AskAlpha/AskBeta Services``, ``123 Bookkeeping``, ``5 Dollar Holler``, and the
hash-suffixed dupes a non-isolated test run can leave behind) match real
catalog rows by shape. This script finds them by name and SOFT-deletes them
(``is_active = 0``) so they drop out of every public surface while staying
fully recoverable — it never hard-deletes.

DEFAULT IS DRY-RUN. It prints every match (table, id, entity_type, name) plus a
total and a per-pattern breakdown, and writes NOTHING. Pass ``--apply`` to
commit the soft-delete (only rows that are currently active are touched).

    .venv\\Scripts\\python.exe scripts\\purge_test_fixtures.py            # DRY RUN
    .venv\\Scripts\\python.exe scripts\\purge_test_fixtures.py --apply    # writes

PROD GATE (CLAUDE.md): on prod this is a prod data op — run the dry-run, show
Casey the counts, get approval, THEN a human runs ``--apply``. The agent never
runs ``--apply`` against prod.

Scope: the live business catalog only — ``entities`` rows of type
``commercial``/``place`` and all ``providers``. Event/program entities are not
touched (real events are not named with these fixture patterns; a hash-suffixed
event in a dev DB is test pollution, out of scope here).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# Repo root on sys.path (``python scripts/...`` does not set PYTHONPATH).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Entity, Provider  # noqa: E402


def _sanitized_target() -> str:
    """The resolved DB target with any credentials stripped — safe to print.

    The repo's .env can point DATABASE_URL at the production Railway Postgres,
    so the operator must always SEE where a run is aimed before --apply writes.
    """
    url = DATABASE_URL or "(unset)"
    # Strip a ``user:pass@`` userinfo segment if present.
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        rest = rest.split("@", 1)[1]
        url = f"{scheme}://{rest}"
    return url

# Entity types that make up the live business catalog. Events/programs are out
# of scope (see module docstring).
CATALOG_ENTITY_TYPES: tuple[str, ...] = ("commercial", "place")

# Named seed/fixture patterns. A row matches if ANY of these match its name;
# the first match supplies the "reason" label for the dry-run breakdown.
# The hash token \b[0-9a-f]{8}\b targets the uuid4-prefix suffix that
# fixtures/dedup dupes carry (e.g. "Acme Plumbing 1400bbd7").
SEED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("acme plumbing", re.compile(r"acme plumbing", re.IGNORECASE)),
    ("acme operator", re.compile(r"acme operator", re.IGNORECASE)),
    ("test fixture", re.compile(r"test fixture", re.IGNORECASE)),
    ("operator verified", re.compile(r"operator verified", re.IGNORECASE)),
    ("sentinel", re.compile(r"sentinel", re.IGNORECASE)),
    ("hex8 token", re.compile(r"\b[0-9a-f]{8}\b", re.IGNORECASE)),
    (
        "numeric bookkeeping/holler",
        re.compile(r"^\d+ (bookkeeping|dollar holler)", re.IGNORECASE),
    ),
    ("askalpha", re.compile(r"askalpha", re.IGNORECASE)),
    ("askbeta", re.compile(r"askbeta", re.IGNORECASE)),
)


@dataclass(frozen=True)
class Match:
    table: str
    row_id: str
    entity_type: str | None
    name: str
    is_active: bool
    reason: str


def match_reason(name: str | None) -> str | None:
    """Return the first matching pattern label, or None if the name is clean."""
    if not name:
        return None
    for label, pattern in SEED_PATTERNS:
        if pattern.search(name):
            return label
    return None


def find_matches(session) -> list[Match]:
    """Collect all seed-pattern matches across the live business catalog."""
    matches: list[Match] = []

    entity_rows = session.query(
        Entity.id, Entity.name, Entity.entity_type, Entity.is_active
    ).filter(Entity.entity_type.in_(CATALOG_ENTITY_TYPES))
    for row_id, name, entity_type, is_active in entity_rows:
        reason = match_reason(name)
        if reason is not None:
            matches.append(
                Match("entities", row_id, entity_type, name, bool(is_active), reason)
            )

    provider_rows = session.query(
        Provider.id, Provider.provider_name, Provider.is_active
    )
    for row_id, name, is_active in provider_rows:
        reason = match_reason(name)
        if reason is not None:
            matches.append(
                Match("providers", row_id, None, name, bool(is_active), reason)
            )

    return matches


def _print_report(matches: list[Match]) -> None:
    by_pattern: Counter[str] = Counter()
    by_table: Counter[str] = Counter()
    active = 0
    for m in matches:
        by_pattern[m.reason] += 1
        by_table[m.table] += 1
        if m.is_active:
            active += 1

    print("=== test-fixture purge — matches ===")
    for m in sorted(matches, key=lambda x: (x.table, x.name.lower())):
        flag = "" if m.is_active else "  (already inactive)"
        et = f" [{m.entity_type}]" if m.entity_type else ""
        print(f"  {m.table:9} {m.row_id}{et}  {m.name!r}  <{m.reason}>{flag}")

    print(f"\ntotal matched: {len(matches)}   (currently active: {active})")
    print("by table:")
    for tbl, n in by_table.most_common():
        print(f"  {n:>4}  {tbl}")
    print("by pattern:")
    for label, n in by_pattern.most_common():
        print(f"  {n:>4}  {label}")


def run(*, apply: bool = False, confirm: bool = False, session=None) -> Counter:
    """Find matches and (optionally) soft-delete the active ones.

    Returns a Counter with ``matched``, ``active``, and ``soft_deleted`` keys.
    Dry-run (the default) writes nothing. ``--apply`` additionally requires
    ``confirm=True`` (CLI: ``--confirm``) so a write is never one flag away from
    a prod-pointed run.
    """
    own_session = session is None
    session = session or SessionLocal()
    counts: Counter = Counter()
    try:
        print(f"DB target: {_sanitized_target()}\n")
        matches = find_matches(session)
        _print_report(matches)
        counts["matched"] = len(matches)
        active_ids = {
            (m.table, m.row_id) for m in matches if m.is_active
        }
        counts["active"] = len(active_ids)

        if not apply:
            print(
                "\nDRY RUN — no rows written. Re-run with --apply --confirm to "
                "soft-delete the active matches above."
            )
            return counts

        if not confirm:
            print(
                "\nREFUSING TO WRITE — --apply requires --confirm. Re-read the DB "
                f"target above ({_sanitized_target()}) and re-run with both flags "
                "if it is correct."
            )
            return counts

        deleted = 0
        for m in matches:
            if not m.is_active:
                continue
            model = Entity if m.table == "entities" else Provider
            obj = session.get(model, m.row_id)
            if obj is not None and obj.is_active:
                obj.is_active = False
                deleted += 1
        session.commit()
        counts["soft_deleted"] = deleted
        print(f"\nAPPLIED — soft-deleted {deleted} active fixture row(s) (is_active=0).")
        return counts
    finally:
        if own_session:
            session.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Soft-delete the active matches (default: dry-run, writes nothing).",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required alongside --apply to actually write (guards prod-pointed runs).",
    )
    args = parser.parse_args(argv)
    run(apply=args.apply, confirm=args.confirm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
