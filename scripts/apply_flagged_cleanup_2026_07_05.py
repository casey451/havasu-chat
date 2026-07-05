"""Session 6d — flagged-listing cleanup (GATED, dry-run default).

Deactivate/collapse the UNAMBIGUOUS flagged listings from the two Phase-2 website
CSVs. Conservative by design: garbled-but-maybe-real names are HELD (not here).

Targets are resolved by NAME against the two filled CSVs (never hand-keyed IDs):
  docs/audits/2026-07/completeness_eatdrink_websites_filled_2026-07-05.csv
  docs/audits/2026-07/completeness_homeservices_websites_filled_2026-07-05.csv

Ops:
  * DEACTIVATE (category-placeholder / out-of-area / mis-categorized) —
    Entity.is_active=False + cascade every Provider.is_active=False.
  * DEACTIVATE (verify-then) — same, but only for names NOT passed as still-open
    via ``--verify-open`` (a human/agent closure check gates these two).
  * COLLAPSE (dup pair) — fold the orphan into the fuller-named survivor via
    app.contrib.provider_merge.merge_providers (gap-fill survivor, repoint FKs,
    retire orphan + redirect). Mirrors Session 6a's collapse.

Skip guards (re-checked live): verified / claimed (Claim.status=='verified') /
sponsored / already-inactive are SKIPPED and reported. A name matching 0 or >1
CSV rows, or a missing/mismatched entity, is reported and skipped (no guessing).

Reversible: ``--apply`` writes ONE transaction + an undo CSV; reverse with
``--reactivate-from <undo.csv> --apply`` (collapse reversal is best-effort, same
caveat as merge_providers / the 6a collapse).

PROD GATE (CLAUDE.md): dry-run -> paste counts -> Casey approves -> apply.

    .venv\\Scripts\\python.exe scripts/apply_flagged_cleanup_2026_07_05.py
    .venv\\Scripts\\python.exe scripts/apply_flagged_cleanup_2026_07_05.py --apply --undo-csv undo_flagged_cleanup_2026-07-05.csv
    .venv\\Scripts\\python.exe scripts/apply_flagged_cleanup_2026_07_05.py --reactivate-from undo_flagged_cleanup_2026-07-05.csv --apply
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.contrib.provider_merge import merge_providers  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Claim, Entity, Provider  # noqa: E402

_CSVS = (
    _ROOT / "docs" / "audits" / "2026-07" / "completeness_eatdrink_websites_filled_2026-07-05.csv",
    _ROOT / "docs" / "audits" / "2026-07" / "completeness_homeservices_websites_filled_2026-07-05.csv",
)

# --- target lists (resolved by NAME from the CSVs above) --------------------
_DEACTIVATE = {
    "placeholder": ["Air conditioning contractor", "Back Flow Preventer",
                    "Landscape And Yard Restoration"],
    "out-of-area": ["ClearPath HVAC & Duct Cleaning Co.", "Phoenix BestPrice Solar",
                    "Estrella Pool & Spa Repairs"],
    "mis-categorized": ["DELI LAUNDROMAT"],
}
_VERIFY_DEACTIVATE = ["Penthouse Budget Storage", "Applied Electric LLC"]
# (orphan_name, survivor_name) — survivor is the fuller-named, kept entry.
_COLLAPSE = [
    ("The Spot", "The Spot - Pizza Arcade & More"),
    ("Wolfie's", "Wolfie's Hawaiian inspired Bbq"),
]


def _norm(s: str) -> str:
    return " ".join((s or "").split()).strip().lower()


def _load_name_index() -> dict[str, list[str]]:
    """name(normalized) -> [entity_id, ...] from both filled CSVs."""
    idx: dict[str, list[str]] = {}
    for path in _CSVS:
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                nm = _norm(r.get("name", ""))
                eid = (r.get("entity_id") or "").strip()
                if nm and eid:
                    idx.setdefault(nm, []).append(eid)
    return idx


@dataclass
class Plan:
    name: str
    op: str                      # deactivate | collapse | skip
    bucket: str = ""
    detail: str = ""
    skip_reason: str = ""
    entity_id: str = ""
    provider_ids: list[str] = field(default_factory=list)
    # collapse
    survivor_entity_id: str = ""
    keep_provider_id: str = ""
    dup_provider_id: str = ""
    gap_filled: list[str] = field(default_factory=list)
    dup_prior: dict = field(default_factory=dict)


def _resolve(idx: dict[str, list[str]], name: str) -> tuple[str | None, str]:
    ids = idx.get(_norm(name), [])
    if len(ids) == 0:
        return None, "name matched 0 CSV rows"
    if len(ids) > 1:
        return None, f"name matched {len(ids)} CSV rows (ambiguous): {ids}"
    return ids[0], ""


def _protected(ent_id: str, provs: list[Provider], claimed: set[str], now: datetime) -> str | None:
    if ent_id in claimed:
        return "claimed"
    for p in provs:
        if p.verified:
            return "verified"
        tier = (getattr(p, "tier", "") or "").strip()
        if tier not in ("", "free"):
            return "sponsored"
        su = p.sponsored_until
        if su is not None:
            if su.tzinfo is None:
                su = su.replace(tzinfo=UTC)
            if su > now:
                return "sponsored"
    return None


def _primary_provider(provs: list[Provider]) -> Provider | None:
    active = [p for p in provs if p.is_active and not p.draft] or provs
    if not active:
        return None
    return sorted(active, key=lambda p: -(getattr(p, "google_review_count", 0) or 0))[0]


def _build_plans(db, verify_open: set[str]) -> list[Plan]:
    now = datetime.now(UTC)
    idx = _load_name_index()
    claimed = {r[0] for r in db.query(Claim.entity_id).filter(Claim.status == "verified").all()}
    provs_by_entity: dict[str, list[Provider]] = {}
    for p in db.query(Provider).all():
        provs_by_entity.setdefault(p.entity_id, []).append(p)

    plans: list[Plan] = []

    def _deactivate_plan(name: str, bucket: str) -> Plan:
        eid, err = _resolve(idx, name)
        if eid is None:
            return Plan(name, "skip", bucket, skip_reason=err)
        ent = db.get(Entity, eid)
        if ent is None:
            return Plan(name, "skip", bucket, skip_reason="entity not found", entity_id=eid)
        if not ent.is_active:
            return Plan(name, "skip", bucket, skip_reason="already inactive", entity_id=eid)
        provs = provs_by_entity.get(eid, [])
        prot = _protected(eid, provs, claimed, now)
        if prot is not None:
            return Plan(name, "skip", bucket, skip_reason=f"protected: {prot}", entity_id=eid)
        return Plan(name, "deactivate", bucket,
                    detail=f"deactivate + cascade {len(provs)} provider(s)",
                    entity_id=eid, provider_ids=[p.id for p in provs])

    for bucket, names in _DEACTIVATE.items():
        for name in names:
            plans.append(_deactivate_plan(name, bucket))

    for name in _VERIFY_DEACTIVATE:
        if _norm(name) in {_norm(n) for n in verify_open}:
            plans.append(Plan(name, "skip", "verify-then",
                              skip_reason="held: closure check says still OPEN"))
            continue
        plans.append(_deactivate_plan(name, "verify-then"))

    # --- collapses ---
    for orphan_name, survivor_name in _COLLAPSE:
        oid, oerr = _resolve(idx, orphan_name)
        sid, serr = _resolve(idx, survivor_name)
        if oid is None:
            plans.append(Plan(orphan_name, "skip", "collapse", skip_reason=f"orphan: {oerr}"))
            continue
        if sid is None:
            plans.append(Plan(orphan_name, "skip", "collapse",
                              skip_reason=f"survivor '{survivor_name}': {serr}"))
            continue
        o_ent, s_ent = db.get(Entity, oid), db.get(Entity, sid)
        if o_ent is None or s_ent is None:
            plans.append(Plan(orphan_name, "skip", "collapse", skip_reason="orphan/survivor entity not found"))
            continue
        prot = _protected(oid, provs_by_entity.get(oid, []), claimed, now)
        if prot is not None:
            plans.append(Plan(orphan_name, "skip", "collapse", skip_reason=f"orphan protected: {prot}"))
            continue
        dup_prov = _primary_provider(provs_by_entity.get(oid, []))
        keep_prov = _primary_provider(provs_by_entity.get(sid, []))
        if dup_prov is None or keep_prov is None:
            plans.append(Plan(orphan_name, "skip", "collapse",
                              skip_reason="orphan or survivor is not provider-backed"))
            continue
        try:
            mr = merge_providers(db, keep_id=keep_prov.id, dup_id=dup_prov.id, dry_run=True)
        except ValueError as exc:
            plans.append(Plan(orphan_name, "skip", "collapse", skip_reason=f"merge refused: {exc}"))
            continue
        other = [p.id for p in provs_by_entity.get(oid, []) if p.id != dup_prov.id]
        plans.append(Plan(
            orphan_name, "collapse", "collapse",
            detail=f"'{o_ent.name}' → '{s_ent.name}'  gap_fill={mr.gap_filled or '-'}  "
                   f"repoint={mr.repointed or '-'}"
                   + (f"  +{len(other)} other orphan provider(s)" if other else ""),
            entity_id=oid, survivor_entity_id=sid,
            keep_provider_id=keep_prov.id, dup_provider_id=dup_prov.id,
            provider_ids=other, gap_filled=list(mr.gap_filled),
            dup_prior={"is_active": bool(dup_prov.is_active), "draft": bool(dup_prov.draft),
                       "pending_review": bool(getattr(dup_prov, "pending_review", False)),
                       "had_redirect": bool((dup_prov.attributes or {}).get("merged_into_slug"))},
        ))
    return plans


_UNDO_FIELDS = ["op", "entity_id", "name", "provider_ids", "survivor_entity_id",
                "keep_provider_id", "dup_provider_id", "extra_json"]


def _apply_plan(db, pl: Plan) -> None:
    if pl.op == "deactivate":
        ent = db.get(Entity, pl.entity_id)
        if ent is not None:
            ent.is_active = False
        for pid in pl.provider_ids:
            p = db.get(Provider, pid)
            if p is not None and p.is_active:
                p.is_active = False
    elif pl.op == "collapse":
        merge_providers(db, keep_id=pl.keep_provider_id, dup_id=pl.dup_provider_id, dry_run=False)
        for pid in pl.provider_ids:
            p = db.get(Provider, pid)
            if p is not None and p.is_active:
                p.is_active = False


def _undo_row(pl: Plan) -> dict:
    row = {k: "" for k in _UNDO_FIELDS}
    row.update(op=pl.op, entity_id=pl.entity_id, name=pl.name)
    if pl.op == "deactivate":
        row["provider_ids"] = ";".join(pl.provider_ids)
    elif pl.op == "collapse":
        row.update(provider_ids=";".join(pl.provider_ids),
                   survivor_entity_id=pl.survivor_entity_id,
                   keep_provider_id=pl.keep_provider_id, dup_provider_id=pl.dup_provider_id,
                   extra_json=json.dumps({"gap_filled": pl.gap_filled, "dup_prior": pl.dup_prior}))
    return row


def run(apply: bool, undo_csv: str | None, verify_open: set[str]) -> int:
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    with SessionLocal() as db:
        plans = _build_plans(db, verify_open)
        deact = [p for p in plans if p.op == "deactivate"]
        coll = [p for p in plans if p.op == "collapse"]
        skips = [p for p in plans if p.op == "skip"]

        mode = "APPLY (writing)" if apply else "DRY RUN (no writes)"
        print("=" * 86)
        print(f"FLAGGED-LISTING CLEANUP — Session 6d — {mode}")
        print("=" * 86)
        print(f"DB target: …@{redacted}")
        print(f"targets: {len(plans)}   deactivate: {len(deact)}   collapse: {len(coll)}   skip: {len(skips)}\n")

        # deactivations grouped by bucket
        by_bucket: dict[str, list[Plan]] = {}
        for pl in deact:
            by_bucket.setdefault(pl.bucket, []).append(pl)
        print(f"--- DEACTIVATE ({len(deact)}) ---")
        for bucket in ("placeholder", "out-of-area", "mis-categorized", "verify-then"):
            rows = by_bucket.get(bucket, [])
            if not rows:
                continue
            print(f"  {bucket} ({len(rows)}):")
            for pl in rows:
                print(f"        {pl.name[:42]:42s} {pl.entity_id[:8]}  {pl.detail}")

        print(f"\n--- COLLAPSE ({len(coll)}) ---")
        for pl in coll:
            print(f"  {pl.detail}")
            print(f"        orphan={pl.entity_id[:8]}  survivor={pl.survivor_entity_id[:8]}  "
                  f"keep_prov={pl.keep_provider_id[:8]}  dup_prov={pl.dup_provider_id[:8]}")

        print(f"\n--- SKIPPED ({len(skips)}) ---")
        for pl in skips:
            print(f"  [{pl.bucket}] {pl.name[:42]:42s} — {pl.skip_reason}")

        ambiguous = [pl for pl in skips if "matched 0" in pl.skip_reason or "ambiguous" in pl.skip_reason]
        if ambiguous:
            print(f"\n!! NAME-RESOLUTION FAILURES ({len(ambiguous)}) — matched 0 or >1 rows:")
            for pl in ambiguous:
                print(f"     {pl.name[:44]:44s} — {pl.skip_reason}")

        if not apply:
            print("\nDRY RUN — nothing written. After approval, re-run with --apply --undo-csv <path>.")
            return 0

        actionable = deact + coll
        undo_rows = [_undo_row(pl) for pl in actionable]
        for pl in actionable:
            _apply_plan(db, pl)
        if undo_csv:
            with open(undo_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=_UNDO_FIELDS)
                w.writeheader()
                w.writerows(undo_rows)
        db.commit()
        print(f"\nAPPLIED: deactivate={len(deact)} collapse={len(coll)}. Undo: {undo_csv}")
        return 0


def reactivate(undo_csv: str, apply: bool) -> int:
    with SessionLocal() as db:
        n = Counter()
        for r in csv.DictReader(open(undo_csv, newline="", encoding="utf-8")):
            op = r.get("op")
            if op == "deactivate":
                ent = db.get(Entity, r["entity_id"])
                if ent is not None and apply:
                    ent.is_active = True
                for pid in (r.get("provider_ids") or "").split(";"):
                    if pid.strip() and apply:
                        p = db.get(Provider, pid.strip())
                        if p is not None:
                            p.is_active = True
                n["deactivate"] += 1
            elif op == "collapse":
                extra = json.loads(r.get("extra_json") or "{}")
                prior = extra.get("dup_prior", {})
                ent = db.get(Entity, r["entity_id"])
                if ent is not None and apply:
                    ent.is_active = True
                dup = db.get(Provider, r["dup_provider_id"]) if r.get("dup_provider_id") else None
                if dup is not None and apply:
                    dup.is_active = prior.get("is_active", True)
                    dup.draft = prior.get("draft", False)
                    if not prior.get("had_redirect") and dup.attributes:
                        attrs = dict(dup.attributes)
                        attrs.pop("merged_into_slug", None)
                        dup.attributes = attrs
                keep = db.get(Provider, r["keep_provider_id"]) if r.get("keep_provider_id") else None
                if keep is not None and apply:
                    for fld in extra.get("gap_filled", []):
                        setattr(keep, fld, None)
                n["collapse"] += 1
        if apply:
            db.commit()
        verb = "REVERSED" if apply else "would reverse"
        print(f"{verb}: deactivate={n['deactivate']} collapse={n['collapse']}")
        if not apply:
            print("DRY RUN: nothing written. Add --apply to reverse.")
        print("NOTE: collapse reversal does NOT restore inbound-FK repoints or the "
              "DedupeResolution row (reversible-ish, per merge_providers).")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Flagged-listing cleanup (dry-run default).")
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    ap.add_argument("--undo-csv", default="undo_flagged_cleanup_2026-07-05.csv")
    ap.add_argument("--reactivate-from", dest="undo_in", help="undo CSV to reverse a prior apply")
    ap.add_argument("--verify-open", default="",
                    help="';'-separated names confirmed STILL OPEN → held from verify-then deactivate")
    args = ap.parse_args(argv)
    if args.undo_in:
        return reactivate(args.undo_in, args.apply)
    verify_open = {s.strip() for s in args.verify_open.split(";") if s.strip()}
    return run(args.apply, args.undo_csv, verify_open)


if __name__ == "__main__":
    raise SystemExit(main())
