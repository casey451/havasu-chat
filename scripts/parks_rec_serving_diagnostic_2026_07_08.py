"""READ-ONLY diagnostic (2026-07-08): is the "45 live P&R in the feed vs 32 in the
source table" discrepancy a STALE MATERIALIZED SNAPSHOT layer (same DB) or SPLIT
DBs? Runs against whatever DATABASE_URL resolves — in CI, the public-proxy prod DB.

WRITES NOTHING. SELECTs + information_schema only.

Proves the theory from the proxy DB alone (Casey's plan):
 1. status + timestamps for the 3 straggler event UIDs (and the corrected Glow).
 2. enumerate materialized-render tables (name looks like a snapshot/cache OR has a
    JSON/TEXT/blob payload); for each: row count, max timestamp, and whether the
    payload embeds the 3 UIDs or "Jane Camlin".
 3. control: does the corrected Glow appear in events AND in a snapshot layer?
 + two visible-bug checks: Afternoon Enrichment double + Kids Pizza Party pair on
   2026-07-08, and the corrected Glow's exact start time.

    .venv\\Scripts\\python.exe scripts/parks_rec_serving_diagnostic_2026_07_08.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import inspect, text  # noqa: E402

from app.db.database import SessionLocal, engine  # noqa: E402

STRAGGLERS = [
    "613de86b-0843-4d6c-9b8a-5ef08f6dcb3b",  # Free Summer Craft Series 06-29
    "5f76296a-2b6b-4324-968b-ffe6f562c779",  # Creative Mondays - Mosaic Art 07-13
    "c10adfc2-3bfa-4232-a98b-8e361f951850",  # Back to School - Pencil Bag 07-28
]
GLOW_PREFIX = "aa6908c7"  # corrected Glow record Casey saw live
NEEDLES = [*STRAGGLERS, "Jane Camlin"]

# Table-name hints for a materialized render/cache layer.
_SNAP_NAME_RE = ("cache", "snapshot", "rendered", "render", "feed", "page", "html",
                 "day_", "materializ", "_view", "digest")
# Column types whose values can embed an event payload.
_PAYLOAD_TYPES = ("JSON", "JSONB", "TEXT", "VARCHAR", "CHAR", "BLOB", "BYTEA", "CLOB")
# Timestamp-ish column names to report freshness from.
_TS_COLS = ("updated_at", "fetched_at", "created_at", "generated_at", "refreshed_at",
            "last_updated", "as_of")


def _hr(t: str) -> None:
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


def _events_for_uids() -> None:
    _hr("1) events-table state for the 3 stragglers + the corrected Glow")
    with SessionLocal() as db:
        from app.db.models import Event
        for uid in STRAGGLERS:
            ev = db.get(Event, uid)
            if ev is None:
                print(f"  {uid[:8]}  ABSENT from events table")
                continue
            print(f"  {uid[:8]}  status={ev.status!r:<16} date={ev.date} "
                  f"start={ev.start_time} venue={ev.location_name!r} "
                  f"created={ev.created_at} scraped={ev.scraped_at}")
        # corrected Glow — find by prefix / title+date
        rows = db.execute(text(
            "SELECT id, status, date, start_time, location_name, host, created_at "
            "FROM events WHERE id LIKE :pfx OR (lower(title) LIKE '%glow%' "
            "AND date = :d) ORDER BY created_at"
        ), {"pfx": GLOW_PREFIX + "%", "d": date(2026, 7, 8)}).fetchall()
        print("  -- Glow on 2026-07-08 (control) --")
        for r in rows:
            print(f"     id={str(r[0])[:8]} status={r[1]!r} date={r[2]} start={r[3]} "
                  f"venue={r[4]!r} host={r[5]!r}")


def _counts() -> None:
    _hr("2) reconcile the 45-vs-32 count on THIS db")
    with SessionLocal() as db:
        q = lambda s, p=None: db.execute(text(s), p or {}).scalar()  # noqa: E731
        print("  live events total:                    ",
              q("SELECT count(*) FROM events WHERE status='live'"))
        print("  live w/ source_url #cal:              ",
              q("SELECT count(*) FROM events WHERE status='live' "
                "AND source_url LIKE '%/185/Parks-Recreation#cal|%'"))
        print("  live w/ source LIKE %parks_rec%:      ",
              q("SELECT count(*) FROM events WHERE status='live' AND source LIKE '%parks_rec%'"))
        print("  live P&R (either, my quarantine set):  ",
              q("SELECT count(*) FROM events WHERE status='live' AND "
                "(source LIKE '%parks_rec%' OR source_url LIKE '%/185/Parks-Recreation#cal|%')"))
        print("  pending_review P&R:                   ",
              q("SELECT count(*) FROM events WHERE status='pending_review' AND "
                "(source LIKE '%parks_rec%' OR source_url LIKE '%/185/Parks-Recreation#cal|%')"))
        print("  live events w/ 'Jane Camlin' in body: ",
              q("SELECT count(*) FROM events WHERE status='live' AND "
                "(location_name LIKE '%Jane Camlin%' OR description LIKE '%Jane Camlin%')"))


def _snapshot_layers() -> None:
    _hr("3) materialized render/cache tables + payload search for the stragglers")
    insp = inspect(engine)
    tables = insp.get_table_names()
    print(f"  {len(tables)} tables total. Scanning snapshot/cache candidates...\n")
    with SessionLocal() as db:
        for t in sorted(tables):
            cols = insp.get_columns(t)
            payload_cols = [c["name"] for c in cols
                            if any(pt in str(c["type"]).upper() for pt in _PAYLOAD_TYPES)]
            name_hit = any(h in t.lower() for h in _SNAP_NAME_RE)
            # candidate = looks like a snapshot by name, OR has a big payload column
            if not (name_hit or payload_cols):
                continue
            try:
                n = db.execute(text(f'SELECT count(*) FROM "{t}"')).scalar()
            except Exception as e:  # noqa: BLE001
                print(f"  [{t}] count failed: {type(e).__name__}")
                continue
            ts_col = next((c["name"] for c in cols if c["name"] in _TS_COLS), None)
            ts = ""
            if ts_col:
                try:
                    maxq = 'SELECT max("' + ts_col + '") FROM "' + t + '"'
                    ts = f" max({ts_col})=" + str(db.execute(text(maxq)).scalar())
                except Exception:  # noqa: BLE001
                    ts = ""
            # search each payload column for the needles
            hits: list[str] = []
            for col in payload_cols:
                for needle in NEEDLES:
                    try:
                        c = db.execute(
                            text(f'SELECT count(*) FROM "{t}" WHERE CAST("{col}" AS TEXT) LIKE :ndl'),
                            {"ndl": f"%{needle}%"},
                        ).scalar()
                    except Exception:  # noqa: BLE001
                        c = None
                    if c:
                        label = needle[:8] if needle in STRAGGLERS else needle
                        hits.append(f"{col}~{label}:{c}")
            flag = "  <<< PAYLOAD MATCH" if hits else ""
            print(f"  [{t}]  rows={n}{ts}  payload_cols={payload_cols or '-'}{flag}")
            if hits:
                print(f"        HITS: {', '.join(hits)}")


def _visible_bugs() -> None:
    _hr("4) the two visible-bug spot checks on 2026-07-08")
    with SessionLocal() as db:
        def show(label: str, like: str) -> None:
            rows = db.execute(text(
                "SELECT id, status, start_time, location_name, title FROM events "
                "WHERE date=:d AND lower(title) LIKE :like ORDER BY start_time"
            ), {"d": date(2026, 7, 8), "like": like}).fetchall()
            print(f"  {label} (2026-07-08):")
            for r in rows:
                print(f"     [{r[1]}] {r[2]} {r[3]!r:<34} {r[4]!r}  ({str(r[0])[:8]})")
            if not rows:
                print("     (none)")
        show("Afternoon Enrichment", "%afternoon enrichment%")
        show("Kids Pizza Party", "%pizza party%")


if __name__ == "__main__":
    print(f"DATABASE host (redacted creds): {engine.url.host}:{engine.url.port}/{engine.url.database}")
    _events_for_uids()
    _counts()
    _snapshot_layers()
    _visible_bugs()
    print("\n(read-only diagnostic complete — no writes)")
