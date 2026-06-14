"""Apply the 2026-06-13 entity_categories audit (GATED — dry-run by default).

The directory category/leaf pages read ``entity_categories`` (a finer tree than
``providers.primary_category``). A name+Google-type sweep found mappings whose
assigned leaf disagrees with what the business clearly is — e.g. "Whiz Kid
Computer Services / Ink & Toner" mapped to *Tattoo & Piercing* because an
auto-classifier matched "Ink". This script moves each flagged row's
``entity_categories.category_id`` to the suggested leaf.

    DEFAULT  = DRY RUN. Prints move counts + a sample. Writes NOTHING.
    --apply  = perform writes. Snapshots before/after to a timestamped JSON for
               one-command rollback. Follows dry-run -> counts -> approval.

Reads ``entity_category_audit_2026-06-13.csv`` (cols: ec_id, suggested_cat_id, ...).
To reject a move, delete its row or blank ``suggested_cat_id``.
Uses DATABASE_URL from .env; run against prod only after Casey approves the counts.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import psycopg2

_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = _ROOT / "entity_category_audit_2026-06-13.csv"


def _dsn() -> dict:
    env = (_ROOT / ".env").read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"^DATABASE_URL=(.+)$", env, re.M)
    if not m:
        raise SystemExit("DATABASE_URL not found in .env")
    url = m.group(1).strip().strip('"').replace("+psycopg2", "")
    u = urlparse(url)
    return dict(host=u.hostname, port=u.port, user=u.username,
                password=u.password, dbname=(u.path or "/").lstrip("/").strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    ap.add_argument("--apply", action="store_true", help="perform writes (GATED)")
    ap.add_argument("--limit-samples", type=int, default=15)
    args = ap.parse_args()

    rows = [r for r in csv.DictReader(open(args.csv, newline="", encoding="utf-8"))
            if (r.get("suggested_cat_id") or "").strip()]
    moves = Counter((r["assigned_leaf"], r["suggested_leaf"]) for r in rows)

    print(f"\nEntity-category audit CSV: {args.csv}")
    print(f"Proposed remaps: {len(rows)} mappings")
    print("\n  count   assigned_leaf -> suggested_leaf")
    for (a, b), n in moves.most_common():
        print(f"  {n:5d}   {a} -> {b}")
    print(f"\nSample (first {args.limit_samples}):")
    for r in rows[: args.limit_samples]:
        print(f"  {r['name'][:44]:44s} {r['assigned_leaf']} -> {r['suggested_leaf']}")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply after approval.")
        return 0

    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    conn = psycopg2.connect(**_dsn())
    cur = conn.cursor()
    snapshot: list[dict] = []
    changed = 0
    try:
        for r in rows:
            ec_id = int(r["ec_id"])
            new_cat = int(r["suggested_cat_id"])
            cur.execute("select category_id from entity_categories where id=%s", (ec_id,))
            row = cur.fetchone()
            if row is None:
                print(f"  ! ec_id {ec_id} not found ({r['name']!r})")
                continue
            old_cat = row[0]
            if old_cat == new_cat:
                continue  # already applied
            snapshot.append({"ec_id": ec_id, "name": r["name"],
                             "old_category_id": old_cat, "new_category_id": new_cat,
                             "assigned_leaf": r["assigned_leaf"], "suggested_leaf": r["suggested_leaf"]})
            cur.execute("update entity_categories set category_id=%s where id=%s and category_id=%s",
                        (new_cat, ec_id, old_cat))
            changed += cur.rowcount
        snap_path = _ROOT / f"apply_entity_category_audit_snapshot_{ts}.json"
        snap_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        conn.commit()
        print(f"\nAPPLIED: {changed} entity_category rows remapped.")
        print(f"Rollback snapshot: {snap_path}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
