"""Session 6d — Beauty dup collapse (GATED, dry-run default).

Collapse the two duplicate "Number One Nails" rows into the canonical survivor
"Number One Nail Expert & More". Resolved by explicit ENTITY_ID (the two orphans
share the same name, so name resolution is ambiguous — hence IDs, not names).
The survivor's website (its FB page) is set by the parallel website backfill.

Mirrors the Session 6a / flagged-cleanup collapse: fold each orphan into the
survivor via app.contrib.provider_merge.merge_providers (gap-fill survivor,
repoint inbound FKs, retire orphan provider + Entity, 301 redirect).

Skip guards (live): orphan verified / claimed / sponsored / already-inactive, or
orphan/survivor not provider-backed, are SKIPPED and reported.

Reversible: ``--apply`` writes ONE transaction + an undo CSV; reverse with
``--reactivate-from <undo.csv> --apply`` (collapse reversal is best-effort, same
caveat as merge_providers).

PROD GATE (CLAUDE.md): dry-run -> counts -> Casey approves -> apply.

    .venv\\Scripts\\python.exe scripts/apply_beauty_dup_collapse_2026_07_05.py
    .venv\\Scripts\\python.exe scripts/apply_beauty_dup_collapse_2026_07_05.py --apply --undo-csv undo_beauty_collapse_2026-07-05.csv
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

_SURVIVOR = "78950a4f-57a2-40e7-aa9c-c10348b35cd5"  # Number One Nail Expert & More
_ORPHANS = [
    "a6b38893-359b-4c95-91fd-a8b239e2ed41",  # Number One Nails
    "acae4100-f4c0-4574-8d87-2302784c2baa",  # Number One Nails
]


@dataclass
class Plan:
    op: str                      # collapse | skip
    orphan_id: str
    orphan_name: str = ""
    detail: str = ""
    skip_reason: str = ""
    survivor_id: str = ""
    keep_provider_id: str = ""
    dup_provider_id: str = ""
    other_provider_ids: list[str] = field(default_factory=list)
    gap_filled: list[str] = field(default_factory=list)
    dup_prior: dict = field(default_factory=dict)


def _protected(eid: str, provs: list[Provider], claimed: set[str], now: datetime) -> str | None:
    if eid in claimed:
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


def _build_plans(db) -> list[Plan]:
    now = datetime.now(UTC)
    claimed = {r[0] for r in db.query(Claim.entity_id).filter(Claim.status == "verified").all()}
    provs_by_entity: dict[str, list[Provider]] = {}
    for p in db.query(Provider).filter(
            Provider.entity_id.in_([_SURVIVOR, *_ORPHANS])).all():
        provs_by_entity.setdefault(p.entity_id, []).append(p)

    survivor = db.get(Entity, _SURVIVOR)
    plans: list[Plan] = []
    for oid in _ORPHANS:
        o_ent = db.get(Entity, oid)
        name = o_ent.name if o_ent else "(missing)"
        if o_ent is None:
            plans.append(Plan("skip", oid, name, skip_reason="orphan entity not found"))
            continue
        if survivor is None:
            plans.append(Plan("skip", oid, name, skip_reason="survivor entity not found"))
            continue
        if not o_ent.is_active:
            plans.append(Plan("skip", oid, name, skip_reason="orphan already inactive"))
            continue
        prot = _protected(oid, provs_by_entity.get(oid, []), claimed, now)
        if prot is not None:
            plans.append(Plan("skip", oid, name, skip_reason=f"orphan protected: {prot}"))
            continue
        dup_prov = _primary_provider(provs_by_entity.get(oid, []))
        keep_prov = _primary_provider(provs_by_entity.get(_SURVIVOR, []))
        if dup_prov is None or keep_prov is None:
            plans.append(Plan("skip", oid, name, skip_reason="orphan or survivor not provider-backed"))
            continue
        try:
            mr = merge_providers(db, keep_id=keep_prov.id, dup_id=dup_prov.id, dry_run=True)
        except ValueError as exc:
            plans.append(Plan("skip", oid, name, skip_reason=f"merge refused: {exc}"))
            continue
        other = [p.id for p in provs_by_entity.get(oid, []) if p.id != dup_prov.id]
        plans.append(Plan(
            "collapse", oid, name,
            detail=f"'{o_ent.name}' → '{survivor.name}'  gap_fill={mr.gap_filled or '-'}  "
                   f"repoint={mr.repointed or '-'}"
                   + (f"  +{len(other)} other orphan provider(s)" if other else ""),
            survivor_id=_SURVIVOR, keep_provider_id=keep_prov.id, dup_provider_id=dup_prov.id,
            other_provider_ids=other, gap_filled=list(mr.gap_filled),
            dup_prior={"is_active": bool(dup_prov.is_active), "draft": bool(dup_prov.draft),
                       "had_redirect": bool((dup_prov.attributes or {}).get("merged_into_slug"))},
        ))
    return plans


_UNDO_FIELDS = ["op", "orphan_id", "survivor_id", "keep_provider_id", "dup_provider_id",
                "other_provider_ids", "extra_json"]


def _undo_row(pl: Plan) -> dict:
    return {
        "op": pl.op, "orphan_id": pl.orphan_id, "survivor_id": pl.survivor_id,
        "keep_provider_id": pl.keep_provider_id, "dup_provider_id": pl.dup_provider_id,
        "other_provider_ids": ";".join(pl.other_provider_ids),
        "extra_json": json.dumps({"gap_filled": pl.gap_filled, "dup_prior": pl.dup_prior}),
    }


def run(apply: bool, undo_csv: str | None) -> int:
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    with SessionLocal() as db:
        plans = _build_plans(db)
        coll = [p for p in plans if p.op == "collapse"]
        skips = [p for p in plans if p.op == "skip"]

        mode = "APPLY (writing)" if apply else "DRY RUN (no writes)"
        print("=" * 84)
        print(f"BEAUTY DUP COLLAPSE (Number One Nails) — Session 6d — {mode}")
        print("=" * 84)
        print(f"DB target: …@{redacted}")
        print(f"collapse: {len(coll)}   skip: {len(skips)}\n")
        for pl in coll:
            print(f"  {pl.detail}")
            print(f"        orphan={pl.orphan_id[:8]}  survivor={pl.survivor_id[:8]}  "
                  f"keep_prov={pl.keep_provider_id[:8]}  dup_prov={pl.dup_provider_id[:8]}")
        for pl in skips:
            print(f"  SKIP {pl.orphan_id[:8]} {pl.orphan_name} — {pl.skip_reason}")

        if not apply:
            print("\nDRY RUN — nothing written. After approval, re-run with --apply --undo-csv <path>.")
            return 0

        undo_rows = [_undo_row(pl) for pl in coll]
        for pl in coll:
            merge_providers(db, keep_id=pl.keep_provider_id, dup_id=pl.dup_provider_id, dry_run=False)
            for pid in pl.other_provider_ids:
                p = db.get(Provider, pid)
                if p is not None and p.is_active:
                    p.is_active = False
        if undo_csv:
            with open(undo_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=_UNDO_FIELDS)
                w.writeheader()
                w.writerows(undo_rows)
        db.commit()
        print(f"\nAPPLIED: collapse={len(coll)}. Undo: {undo_csv}")
        return 0


def reactivate(undo_csv: str, apply: bool) -> int:
    with SessionLocal() as db:
        n = Counter()
        for r in csv.DictReader(open(undo_csv, newline="", encoding="utf-8")):
            if r.get("op") != "collapse":
                continue
            extra = json.loads(r.get("extra_json") or "{}")
            prior = extra.get("dup_prior", {})
            ent = db.get(Entity, r["orphan_id"])
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
        print(f"{verb}: collapse={n['collapse']}")
        if not apply:
            print("DRY RUN: nothing written. Add --apply to reverse.")
        print("NOTE: collapse reversal does NOT restore inbound-FK repoints or the "
              "DedupeResolution row (reversible-ish, per merge_providers).")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Beauty dup collapse (dry-run default).")
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    ap.add_argument("--undo-csv", default="undo_beauty_collapse_2026-07-05.csv")
    ap.add_argument("--reactivate-from", dest="undo_in", help="undo CSV to reverse a prior apply")
    args = ap.parse_args(argv)
    if args.undo_in:
        return reactivate(args.undo_in, args.apply)
    return run(args.apply, args.undo_csv)


if __name__ == "__main__":
    raise SystemExit(main())
