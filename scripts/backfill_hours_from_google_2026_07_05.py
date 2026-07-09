"""Backfill structured hours from google_hours — $0, DB-only (GATED, dry-run default).

Consistency cleanup (docs/SESSION_HOURS_INGESTION_PLAN_2026-07-05.md part b): the
bulk Places loader historically set only ``Provider.google_hours``, leaving
``hours_structured`` NULL and 0 Entity ``Hours`` rows — so the structured Hours
table held only ~8 rows even though hours render fine via the ``google_hours``
fallback. This backfills, for every Provider whose ``google_hours`` converts to
non-empty structured hours:

  * ``Provider.hours_structured`` = converted (only when currently empty — never
    overwrites operator-curated structured hours), and
  * Entity ``Hours`` rows materialized from the effective structured hours —
    ONLY for entities that currently have 0 ``Hours`` rows (never clobbers
    existing/curated rows; those are reported and left alone).

**No Google API calls** — pure DB reads of the stored ``google_hours`` + the
existing ``places_hours_to_structured`` converter. Reversible via a JSON undo
snapshot: restores the prior ``hours_structured`` and deletes the ``Hours`` rows
we inserted (target entities had 0 before, so deletion is exact).

PROD GATE (CLAUDE.md): dry-run -> counts -> Casey approves -> apply.

    .venv\\Scripts\\python.exe scripts/backfill_hours_from_google_2026_07_05.py
    .venv\\Scripts\\python.exe scripts/backfill_hours_from_google_2026_07_05.py --apply --undo-json undo_hours_backfill_2026-07-05.json
    .venv\\Scripts\\python.exe scripts/backfill_hours_from_google_2026_07_05.py --reactivate-from undo_hours_backfill_2026-07-05.json --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.contrib.hours_helper import places_hours_to_structured  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.entity_backfill import _WEEKDAY_KEYS, _parse_hours_time  # noqa: E402
from app.db.models import Entity, Hours, Provider  # noqa: E402

# Raw enrichment responses — re-parse source for the $0 top-up of the NULL slice.
_ENRICHMENT_JSONL = _ROOT / "scripts" / "output" / "places_pull" / "enrichment_raw.jsonl"


def _materialize_rows(hs: dict) -> list[tuple[int, object, object]]:
    """(day_of_week, opens_at, closes_at) rows — mirrors entity_dual_write."""
    rows: list[tuple[int, object, object]] = []
    if not isinstance(hs, dict):
        return rows
    for di, day_key in enumerate(_WEEKDAY_KEYS):
        spans = hs.get(day_key)
        if not isinstance(spans, list):
            continue
        for span in spans:
            if not isinstance(span, dict):
                continue
            open_raw = span.get("open") or span.get("opens")
            close_raw = span.get("close") or span.get("closes") or span.get("closes_at")
            ot = _parse_hours_time(str(open_raw) if open_raw is not None else None)
            ct = _parse_hours_time(str(close_raw) if close_raw is not None else None)
            if ot is None and ct is None:
                continue
            rows.append((di, ot, ct))
    return rows


@dataclass
class Plan:
    provider_id: str
    entity_id: str
    name: str
    set_structured: bool          # write hours_structured
    insert_hours: bool            # materialize Hours rows
    prior_structured_empty: bool
    converted: dict = field(default_factory=dict)
    hours_rows: list = field(default_factory=list)


def _build_plans(db) -> tuple[list[Plan], Counter, dict]:
    plans: list[Plan] = []
    counts: Counter = Counter()

    provs = (
        db.query(Provider)
        .filter(Provider.google_hours.isnot(None))
        .order_by(Provider.id)
        .all()
    )
    counts["providers_with_google_hours"] = len(provs)

    # Hours-row counts per entity in ONE pass.
    hours_count: dict[str, int] = {}
    for (eid,) in db.query(Hours.entity_id).all():
        hours_count[eid] = hours_count.get(eid, 0) + 1

    total_hours_rows = 0
    for p in provs:
        gh = p.google_hours
        if not isinstance(gh, dict):
            counts["skip_google_hours_not_dict"] += 1
            continue
        converted = places_hours_to_structured(gh)
        if not converted:
            counts["skip_not_convertible"] += 1
            continue
        if not p.entity_id or db.get(Entity, p.entity_id) is None:
            counts["skip_no_entity"] += 1
            continue

        cur_hs = p.hours_structured
        structured_empty = not (isinstance(cur_hs, dict) and cur_hs) and not (
            isinstance(cur_hs, str) and cur_hs.strip() not in ("", "{}")
        )
        effective = cur_hs if (isinstance(cur_hs, dict) and cur_hs) else converted
        n_hours = hours_count.get(p.entity_id, 0)

        set_structured = structured_empty
        insert_hours = n_hours == 0
        rows = _materialize_rows(effective) if insert_hours else []

        if not set_structured and not insert_hours:
            counts["skip_already_complete"] += 1
            continue
        if not insert_hours and set_structured:
            counts["structured_only_has_hours"] += 1  # has Hours rows already; just fill structured
        if insert_hours:
            counts["would_insert_hours_entities"] += 1
            total_hours_rows += len(rows)
        if set_structured:
            counts["would_set_structured"] += 1

        plans.append(Plan(
            provider_id=p.id, entity_id=p.entity_id, name=p.provider_name or "",
            set_structured=set_structured, insert_hours=insert_hours,
            prior_structured_empty=structured_empty, converted=converted, hours_rows=rows,
        ))
    counts["would_insert_hours_rows_total"] = total_hours_rows

    # NULL-google_hours slice (the optional paid/JSONL top-up population).
    null_slice = (
        db.query(Provider)
        .filter(Provider.google_hours.is_(None), Provider.is_active.is_(True), Provider.draft.is_(False))
        .count()
    )
    topup = {"null_google_hours_active": null_slice,
             "enrichment_jsonl_exists": _ENRICHMENT_JSONL.exists(),
             "enrichment_jsonl_path": str(_ENRICHMENT_JSONL.relative_to(_ROOT))}
    return plans, counts, topup


def run(apply: bool, undo_json: str | None) -> int:
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    with SessionLocal() as db:
        plans, counts, topup = _build_plans(db)

        mode = "APPLY (writing)" if apply else "DRY RUN (no writes)"
        print("=" * 84)
        print(f"HOURS BACKFILL FROM google_hours ($0, DB-only) — {mode}")
        print("=" * 84)
        print(f"DB target: …@{redacted}\n")
        print(f"Providers with google_hours:        {counts['providers_with_google_hours']}")
        print(f"  would SET hours_structured:       {counts['would_set_structured']}")
        print(f"  would INSERT Hours rows (entities):{counts['would_insert_hours_entities']}"
              f"  ({counts['would_insert_hours_rows_total']} Hours rows)")
        print(f"  structured-only (entity has Hours):{counts['structured_only_has_hours']}")
        print("  skipped:")
        for k in ("skip_already_complete", "skip_not_convertible", "skip_no_entity",
                  "skip_google_hours_not_dict"):
            if counts[k]:
                print(f"      {k}: {counts[k]}")
        print(f"\nactionable plans: {len(plans)}")
        for pl in plans[:8]:
            print(f"    {pl.name[:36]:36s} set_struct={pl.set_structured} "
                  f"insert_hours={pl.insert_hours} ({len(pl.hours_rows)} rows)")
        if len(plans) > 8:
            print(f"    … +{len(plans) - 8} more")

        print("\n--- optional top-up slice (part c — NOT done here) ---")
        print(f"  Providers with NULL google_hours (active): {topup['null_google_hours_active']}")
        print(f"  enrichment_raw.jsonl exists (re-parse for $0)? {topup['enrichment_jsonl_exists']} "
              f"[{topup['enrichment_jsonl_path']}]")

        if not apply:
            print("\nDRY RUN — nothing written. After approval, re-run with --apply --undo-json <path>.")
            return 0

        undo: list[dict] = []
        for pl in plans:
            p = db.get(Provider, pl.provider_id)
            undo.append({
                "provider_id": pl.provider_id, "entity_id": pl.entity_id,
                "prior_structured": p.hours_structured if pl.set_structured else "__unchanged__",
                "hours_inserted": pl.insert_hours,
            })
            if pl.set_structured:
                p.hours_structured = pl.converted
            if pl.insert_hours:
                for di, ot, ct in pl.hours_rows:
                    db.add(Hours(entity_id=pl.entity_id, day_of_week=di,
                                 opens_at=ot, closes_at=ct, is_24h=False, notes=None))
        db.commit()
        if undo_json:
            Path(undo_json).write_text(json.dumps(undo, indent=2, default=str), encoding="utf-8")
        print(f"\nAPPLIED: set_structured={counts['would_set_structured']} "
              f"hours_entities={counts['would_insert_hours_entities']} "
              f"hours_rows={counts['would_insert_hours_rows_total']}. Undo: {undo_json}")
        return 0


def reactivate(undo_json: str, apply: bool) -> int:
    data = json.loads(Path(undo_json).read_text(encoding="utf-8"))
    with SessionLocal() as db:
        n = Counter()
        for r in data:
            if apply:
                if r.get("prior_structured") != "__unchanged__":
                    p = db.get(Provider, r["provider_id"])
                    if p is not None:
                        prior = r["prior_structured"]
                        p.hours_structured = prior if isinstance(prior, dict) else None
                        n["restored_structured"] += 1
                if r.get("hours_inserted"):
                    db.query(Hours).filter(Hours.entity_id == r["entity_id"]).delete()
                    n["deleted_hours_entities"] += 1
        if apply:
            db.commit()
        verb = "REVERSED" if apply else "would reverse"
        print(f"{verb}: restored_structured={n['restored_structured']} "
              f"deleted_hours_entities={n['deleted_hours_entities']}")
        if not apply:
            print("DRY RUN: nothing written. Add --apply to reverse.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Backfill structured hours from google_hours (dry-run default).")
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    ap.add_argument("--undo-json", default="undo_hours_backfill_2026-07-05.json")
    ap.add_argument("--reactivate-from", dest="undo_in", help="undo JSON to reverse a prior apply")
    args = ap.parse_args(argv)
    if args.undo_in:
        return reactivate(args.undo_in, args.apply)
    return run(args.apply, args.undo_json)


if __name__ == "__main__":
    raise SystemExit(main())
