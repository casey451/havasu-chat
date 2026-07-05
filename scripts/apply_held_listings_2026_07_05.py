"""Session 6d — held-listings final op (GATED, dry-run default).

Clears the last HELD listings with four op types over a hand-confirmed list, each
entity resolved BY NAME from the banked source CSVs (never hand-keyed IDs):

  * REPOINT   — primary EntityCategory -> a valid level-1 leaf (mirrors
    apply_browse_orphans / apply_final_decisions), + set website if empty.
  * COLLAPSE  — fold an orphan into its survivor via merge_providers (mirrors
    Session 6a), + set the survivor's website if empty.
  * DEACTIVATE — Entity.is_active=False + cascade providers (skips
    verified/claimed/sponsored/inactive).

Sources: browse_orphans_review (provider_name), the eatdrink website CSV (name).
A name matching 0 or >1 rows is reported and skipped. Repoint is corrective, so a
protected (verified) row is repointed anyway and flagged (BMX); collapse +
deactivate skip protected orphans.

Reversible: ``--apply`` writes ONE transaction + an undo CSV; reverse with
``--reactivate-from <undo.csv> --apply`` (collapse reversal best-effort, per
merge_providers).

PROD GATE (CLAUDE.md): dry-run -> counts -> Casey approves -> apply.

    .venv\\Scripts\\python.exe scripts/apply_held_listings_2026_07_05.py
    .venv\\Scripts\\python.exe scripts/apply_held_listings_2026_07_05.py --apply --undo-csv undo_held_listings_2026-07-05.csv
    .venv\\Scripts\\python.exe scripts/apply_held_listings_2026_07_05.py --reactivate-from undo_held_listings_2026-07-05.csv --apply
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
from app.db.models import (  # noqa: E402
    Category,
    Claim,
    ContactPoint,
    Entity,
    EntityCategory,
    Provider,
)

_AUDIT = _ROOT / "docs" / "audits" / "2026-07"
_CSVS = (
    (_AUDIT / "browse_orphans_review_2026-07-05.csv", "provider_name"),
    (_AUDIT / "completeness_eatdrink_websites_filled_2026-07-05.csv", "name"),
)
_WEB_KINDS = {"website", "web", "url"}

# (name, target_leaf_slug, website_or_None)
_REPOINT: tuple[tuple[str, str, str | None], ...] = (
    ("Lake Havasu City BMX", "parks-and-playgrounds",
     "https://www.usabmx.com/tracks/az-lake-havasu-city-bmx"),
    ("Desert Hawks RC Club", "nonprofits-and-charities", "https://deserthawksrc.club"),
)
# (orphan_name, survivor_name, survivor_website_or_None)
_COLLAPSE: tuple[tuple[str, str, str | None], ...] = (
    ("Lady Lee's", "Lady Lee's Billiards Hall", "https://ladylees.com"),
)
_DEACTIVATE: tuple[str, ...] = (
    "Memory Magic", "The 928 Group", "Cocoloco", "Farmer's Tavern", "Northside Grill",
)


def _norm(s: str) -> str:
    return " ".join((s or "").split()).strip().lower()


def _load_name_index() -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {}
    for path, col in _CSVS:
        for r in csv.DictReader(open(path, newline="", encoding="utf-8")):
            nm = _norm(r.get(col, ""))
            eid = (r.get("entity_id") or "").strip()
            if nm and eid:
                idx.setdefault(nm, []).append(eid)
    return idx


@dataclass
class Plan:
    name: str
    op: str                       # repoint | deactivate | collapse | skip
    detail: str = ""
    skip_reason: str = ""
    entity_id: str = ""
    # repoint
    prim_ec_id: int | None = None
    old_category_id: int | None = None
    target_ec_id: int | None = None
    new_category_id: int | None = None
    mode: str = ""
    # website (rides repoint or collapse)
    web_target: str = ""          # provider | contact_point | ""
    web_provider_id: str = ""
    web_prior_website: str = ""
    web_new_website: str = ""
    web_note: str = ""
    web_entity_id: str = ""       # for collapse the website goes on the SURVIVOR
    # deactivate
    provider_ids: list[str] = field(default_factory=list)
    # collapse
    survivor_id: str = ""
    keep_provider_id: str = ""
    dup_provider_id: str = ""
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


def _web_cp(cps: list[ContactPoint]) -> ContactPoint | None:
    for cp in cps:
        if (cp.kind or "").strip().lower() in _WEB_KINDS and (cp.value or "").strip():
            return cp
    return None


def _primary_provider(provs: list[Provider]) -> Provider | None:
    active = [p for p in provs if p.is_active and not p.draft] or provs
    if not active:
        return None
    return sorted(active, key=lambda p: -(getattr(p, "google_review_count", 0) or 0))[0]


def _plan_website(pl: Plan, db, eid: str, url: str, provs: list, cps: list, prot: str | None) -> None:
    """Fill website fields on ``pl`` for entity ``eid`` (only if empty + not protected)."""
    active = [p for p in provs if p.is_active and not p.draft]
    cur = next((p.website.strip() for p in active if (p.website or "").strip()), "")
    cp = _web_cp(cps)
    current = cur or (cp.value.strip() if cp else "")
    pl.web_entity_id = eid
    if current:
        pl.web_note = f"website already set ({current}) — skipped"
        return
    if prot is not None:
        pl.web_note = f"website skipped (protected: {prot})"
        return
    if active:
        target_p = sorted(active, key=lambda p: -(getattr(p, "google_review_count", 0) or 0))[0]
        pl.web_target = "provider"
        pl.web_provider_id = target_p.id
        pl.web_prior_website = target_p.website or ""
        pl.web_new_website = url
        pl.web_note = f"Provider.website ← {url}"
    else:
        pl.web_target = "contact_point"
        pl.web_new_website = url
        pl.web_note = f"new website ContactPoint ← {url}"


def _build_plans(db) -> list[Plan]:
    now = datetime.now(UTC)
    idx = _load_name_index()
    claimed = {r[0] for r in db.query(Claim.entity_id).filter(Claim.status == "verified").all()}
    cats_by_slug = {c.slug: c for c in db.query(Category).all()}
    leaf_slugs = {s for s, c in cats_by_slug.items() if c.level == 1}
    provs_by_entity: dict[str, list[Provider]] = {}
    for p in db.query(Provider).all():
        provs_by_entity.setdefault(p.entity_id, []).append(p)

    def _resolve(name: str) -> tuple[str | None, str]:
        ids = idx.get(_norm(name), [])
        if len(ids) == 0:
            return None, "name matched 0 CSV rows"
        if len(ids) > 1:
            return None, f"name matched {len(ids)} CSV rows (ambiguous): {ids}"
        return ids[0], ""

    def _primary_ec(eid: str) -> EntityCategory | None:
        return (db.query(EntityCategory)
                .filter(EntityCategory.entity_id == eid, EntityCategory.is_primary.is_(True))
                .first())

    def _cps(eid: str) -> list:
        return db.query(ContactPoint).filter(ContactPoint.entity_id == eid).all()

    plans: list[Plan] = []

    # ---- REPOINT (+ website) ----
    for name, slug, url in _REPOINT:
        eid, err = _resolve(name)
        if eid is None:
            plans.append(Plan(name, "skip", skip_reason=err))
            continue
        ent = db.get(Entity, eid)
        if ent is None:
            plans.append(Plan(name, "skip", skip_reason="entity not found", entity_id=eid))
            continue
        target = cats_by_slug.get(slug)
        if target is None or slug not in leaf_slugs:
            plans.append(Plan(name, "skip", skip_reason=f"target '{slug}' not a live level-1 leaf", entity_id=eid))
            continue
        if not ent.is_active:
            plans.append(Plan(name, "skip", skip_reason="entity inactive", entity_id=eid))
            continue
        prim = _primary_ec(eid)
        if prim is not None and prim.category_id == target.id:
            pl = Plan(name, "repoint", entity_id=eid, mode="already-at-target", detail=f"already on {slug}")
        else:
            existing = (db.query(EntityCategory)
                        .filter(EntityCategory.entity_id == eid, EntityCategory.category_id == target.id)
                        .one_or_none())
            if existing is not None and prim is not None and existing.id != prim.id:
                mode = "swap"
            elif existing is not None and prim is None:
                mode = "promote"
            elif prim is not None:
                mode = "repoint"
            else:
                mode = "insert"
            old = db.get(Category, prim.category_id) if prim else None
            prot = _protected(eid, provs_by_entity.get(eid, []), claimed, now)
            note = f"  [protected:{prot} — repointed anyway]" if prot else ""
            pl = Plan(name, "repoint", entity_id=eid,
                      detail=f"{(old.slug if old else '(none)')} -> {slug} [{mode}]{note}",
                      prim_ec_id=(prim.id if prim else None),
                      old_category_id=(prim.category_id if prim else None),
                      target_ec_id=(existing.id if existing is not None else None),
                      new_category_id=target.id, mode=mode)
        if url:
            prot = _protected(eid, provs_by_entity.get(eid, []), claimed, now)
            _plan_website(pl, db, eid, url, provs_by_entity.get(eid, []), _cps(eid), prot)
        plans.append(pl)

    # ---- COLLAPSE (+ survivor website) ----
    for orphan_name, survivor_name, surv_url in _COLLAPSE:
        oid, oerr = _resolve(orphan_name)
        sid, serr = _resolve(survivor_name)
        if oid is None:
            plans.append(Plan(orphan_name, "skip", skip_reason=f"orphan: {oerr}"))
            continue
        if sid is None:
            plans.append(Plan(orphan_name, "skip", skip_reason=f"survivor '{survivor_name}': {serr}"))
            continue
        o_ent, s_ent = db.get(Entity, oid), db.get(Entity, sid)
        if o_ent is None or s_ent is None:
            plans.append(Plan(orphan_name, "skip", skip_reason="orphan/survivor entity not found"))
            continue
        if not o_ent.is_active:
            plans.append(Plan(orphan_name, "skip", skip_reason="orphan already inactive", entity_id=oid))
            continue
        prot = _protected(oid, provs_by_entity.get(oid, []), claimed, now)
        if prot is not None:
            plans.append(Plan(orphan_name, "skip", skip_reason=f"orphan protected: {prot}", entity_id=oid))
            continue
        dup_prov = _primary_provider(provs_by_entity.get(oid, []))
        keep_prov = _primary_provider(provs_by_entity.get(sid, []))
        if dup_prov is None or keep_prov is None:
            plans.append(Plan(orphan_name, "skip", skip_reason="orphan or survivor not provider-backed", entity_id=oid))
            continue
        try:
            mr = merge_providers(db, keep_id=keep_prov.id, dup_id=dup_prov.id, dry_run=True)
        except ValueError as exc:
            plans.append(Plan(orphan_name, "skip", skip_reason=f"merge refused: {exc}", entity_id=oid))
            continue
        pl = Plan(orphan_name, "collapse", entity_id=oid, survivor_id=sid,
                  detail=f"'{o_ent.name}' → '{s_ent.name}'  gap_fill={mr.gap_filled or '-'}  repoint={mr.repointed or '-'}",
                  keep_provider_id=keep_prov.id, dup_provider_id=dup_prov.id,
                  gap_filled=list(mr.gap_filled),
                  dup_prior={"is_active": bool(dup_prov.is_active), "draft": bool(dup_prov.draft),
                             "had_redirect": bool((dup_prov.attributes or {}).get("merged_into_slug"))})
        if surv_url:
            prot = _protected(sid, provs_by_entity.get(sid, []), claimed, now)
            _plan_website(pl, db, sid, surv_url, provs_by_entity.get(sid, []), _cps(sid), prot)
        plans.append(pl)

    # ---- DEACTIVATE ----
    for name in _DEACTIVATE:
        eid, err = _resolve(name)
        if eid is None:
            plans.append(Plan(name, "skip", skip_reason=err))
            continue
        ent = db.get(Entity, eid)
        if ent is None:
            plans.append(Plan(name, "skip", skip_reason="entity not found", entity_id=eid))
            continue
        if not ent.is_active:
            plans.append(Plan(name, "skip", skip_reason="already inactive", entity_id=eid))
            continue
        provs = provs_by_entity.get(eid, [])
        prot = _protected(eid, provs, claimed, now)
        if prot is not None:
            plans.append(Plan(name, "skip", skip_reason=f"protected: {prot}", entity_id=eid))
            continue
        plans.append(Plan(name, "deactivate", entity_id=eid,
                          detail=f"deactivate + cascade {len(provs)} provider(s)",
                          provider_ids=[p.id for p in provs]))
    return plans


_UNDO_FIELDS = ["op", "name", "entity_id", "prim_ec_id", "old_category_id", "target_ec_id",
                "new_category_id", "mode", "web_target", "web_entity_id", "web_provider_id",
                "web_prior_website", "web_new_website", "provider_ids",
                "survivor_id", "keep_provider_id", "dup_provider_id", "extra_json"]


def _undo_row(pl: Plan) -> dict:
    row = {k: "" for k in _UNDO_FIELDS}
    row.update(op=pl.op, name=pl.name, entity_id=pl.entity_id)
    if pl.op == "repoint":
        row.update(prim_ec_id=pl.prim_ec_id or "", old_category_id=pl.old_category_id or "",
                   target_ec_id=pl.target_ec_id or "", new_category_id=pl.new_category_id or "", mode=pl.mode)
    if pl.web_target:
        row.update(web_target=pl.web_target, web_entity_id=pl.web_entity_id,
                   web_provider_id=pl.web_provider_id, web_prior_website=pl.web_prior_website,
                   web_new_website=pl.web_new_website)
    if pl.op == "deactivate":
        row.update(provider_ids=";".join(pl.provider_ids))
    if pl.op == "collapse":
        row.update(survivor_id=pl.survivor_id, keep_provider_id=pl.keep_provider_id,
                   dup_provider_id=pl.dup_provider_id,
                   extra_json=json.dumps({"gap_filled": pl.gap_filled, "dup_prior": pl.dup_prior}))
    return row


def _apply_plan(db, pl: Plan) -> None:
    if pl.op == "repoint" and pl.mode != "already-at-target":
        prim = db.get(EntityCategory, pl.prim_ec_id) if pl.prim_ec_id else None
        target_ec = db.get(EntityCategory, pl.target_ec_id) if pl.target_ec_id else None
        if pl.mode == "swap":
            if prim is not None:
                prim.is_primary = False
            if target_ec is not None:
                target_ec.is_primary = True
        elif pl.mode == "promote":
            if target_ec is not None:
                target_ec.is_primary = True
        elif pl.mode == "repoint":
            if prim is not None:
                prim.category_id = pl.new_category_id
        elif pl.mode == "insert":
            db.add(EntityCategory(entity_id=pl.entity_id, category_id=pl.new_category_id, is_primary=True))
    if pl.op == "collapse":
        merge_providers(db, keep_id=pl.keep_provider_id, dup_id=pl.dup_provider_id, dry_run=False)
    # website (repoint -> self entity; collapse -> survivor entity)
    if pl.web_target == "provider":
        p = db.get(Provider, pl.web_provider_id)
        if p is not None:
            p.website = pl.web_new_website
    elif pl.web_target == "contact_point":
        db.add(ContactPoint(entity_id=pl.web_entity_id, kind="website",
                            value=pl.web_new_website, is_primary=True, display_order=0))
    if pl.op == "deactivate":
        ent = db.get(Entity, pl.entity_id)
        if ent is not None:
            ent.is_active = False
        for pid in pl.provider_ids:
            p = db.get(Provider, pid)
            if p is not None and p.is_active:
                p.is_active = False


def run(apply: bool, undo_csv: str | None) -> int:
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    with SessionLocal() as db:
        plans = _build_plans(db)
        by = {"repoint": [], "collapse": [], "deactivate": [], "skip": []}
        for pl in plans:
            by[pl.op].append(pl)

        mode = "APPLY (writing)" if apply else "DRY RUN (no writes)"
        print("=" * 88)
        print(f"HELD-LISTINGS FINAL OP — Session 6d — {mode}")
        print("=" * 88)
        print(f"DB target: …@{redacted}")
        websites = sum(1 for pl in plans if pl.web_target)
        print(f"repoint: {len(by['repoint'])}   collapse: {len(by['collapse'])}   "
              f"deactivate: {len(by['deactivate'])}   skip: {len(by['skip'])}   "
              f"(websites set: {websites})\n")

        print(f"--- REPOINT ({len(by['repoint'])}) ---")
        for pl in by["repoint"]:
            web = f"   +web: {pl.web_note}" if pl.web_note else ""
            print(f"  {pl.name[:32]:32s} {pl.entity_id[:8]}  {pl.detail}{web}")
        print(f"\n--- COLLAPSE ({len(by['collapse'])}) ---")
        for pl in by["collapse"]:
            web = f"   +survivor web: {pl.web_note}" if pl.web_note else ""
            print(f"  {pl.name[:26]:26s} {pl.detail}{web}")
            print(f"        orphan={pl.entity_id[:8]} survivor={pl.survivor_id[:8]} "
                  f"keep={pl.keep_provider_id[:8]} dup={pl.dup_provider_id[:8]}")
        print(f"\n--- DEACTIVATE ({len(by['deactivate'])}) ---")
        for pl in by["deactivate"]:
            print(f"  {pl.name[:32]:32s} {pl.entity_id[:8]}  {pl.detail}")
        print(f"\n--- SKIPPED ({len(by['skip'])}) ---")
        for pl in by["skip"]:
            print(f"  {pl.name[:32]:32s} — {pl.skip_reason}")

        nameres = [pl for pl in by["skip"] if "matched 0" in pl.skip_reason or "ambiguous" in pl.skip_reason]
        if nameres:
            print(f"\n!! NAME-RESOLUTION FAILURES ({len(nameres)}):")
            for pl in nameres:
                print(f"     {pl.name} — {pl.skip_reason}")

        if not apply:
            print("\nDRY RUN — nothing written. After approval, re-run with --apply --undo-csv <path>.")
            return 0

        actionable = by["repoint"] + by["collapse"] + by["deactivate"]
        undo_rows = [_undo_row(pl) for pl in actionable]
        for pl in actionable:
            _apply_plan(db, pl)
        if undo_csv:
            with open(undo_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=_UNDO_FIELDS)
                w.writeheader()
                w.writerows(undo_rows)
        db.commit()
        print(f"\nAPPLIED: repoint={len(by['repoint'])} collapse={len(by['collapse'])} "
              f"deactivate={len(by['deactivate'])} websites={websites}. Undo: {undo_csv}")
        return 0


def reactivate(undo_csv: str, apply: bool) -> int:
    with SessionLocal() as db:
        n = Counter()
        for r in csv.DictReader(open(undo_csv, newline="", encoding="utf-8")):
            op = r.get("op")
            if op == "repoint" and r.get("mode") not in ("", "already-at-target"):
                mode = r.get("mode")
                prim = db.get(EntityCategory, int(r["prim_ec_id"])) if r.get("prim_ec_id") else None
                tgt = db.get(EntityCategory, int(r["target_ec_id"])) if r.get("target_ec_id") else None
                if apply:
                    if mode == "swap":
                        if prim is not None:
                            prim.is_primary = True
                        if tgt is not None:
                            tgt.is_primary = False
                    elif mode == "promote":
                        if tgt is not None:
                            tgt.is_primary = False
                    elif mode == "repoint":
                        if prim is not None and r.get("old_category_id"):
                            prim.category_id = int(r["old_category_id"])
                    elif mode == "insert":
                        db.query(EntityCategory).filter(
                            EntityCategory.entity_id == r["entity_id"],
                            EntityCategory.category_id == int(r["new_category_id"])).delete()
                n["repoint"] += 1
            if r.get("web_target") == "provider" and apply:
                p = db.get(Provider, r["web_provider_id"]) if r.get("web_provider_id") else None
                if p is not None:
                    p.website = r.get("web_prior_website") or None
                n["website"] += 1
            elif r.get("web_target") == "contact_point" and apply:
                db.query(ContactPoint).filter(
                    ContactPoint.entity_id == r.get("web_entity_id"), ContactPoint.kind == "website",
                    ContactPoint.value == r.get("web_new_website")).delete()
                n["website"] += 1
            if op == "deactivate" and apply:
                ent = db.get(Entity, r["entity_id"])
                if ent is not None:
                    ent.is_active = True
                for pid in (r.get("provider_ids") or "").split(";"):
                    if pid.strip():
                        p = db.get(Provider, pid.strip())
                        if p is not None:
                            p.is_active = True
                n["deactivate"] += 1
            if op == "collapse" and apply:
                extra = json.loads(r.get("extra_json") or "{}")
                prior = extra.get("dup_prior", {})
                ent = db.get(Entity, r["entity_id"])
                if ent is not None:
                    ent.is_active = True
                dup = db.get(Provider, r["dup_provider_id"]) if r.get("dup_provider_id") else None
                if dup is not None:
                    dup.is_active = prior.get("is_active", True)
                    dup.draft = prior.get("draft", False)
                    if not prior.get("had_redirect") and dup.attributes:
                        attrs = dict(dup.attributes)
                        attrs.pop("merged_into_slug", None)
                        dup.attributes = attrs
                keep = db.get(Provider, r["keep_provider_id"]) if r.get("keep_provider_id") else None
                if keep is not None:
                    for fld in extra.get("gap_filled", []):
                        setattr(keep, fld, None)
                n["collapse"] += 1
        if apply:
            db.commit()
        verb = "REVERSED" if apply else "would reverse"
        print(f"{verb}: repoint={n['repoint']} collapse={n['collapse']} website={n['website']} "
              f"deactivate={n['deactivate']}")
        if not apply:
            print("DRY RUN: nothing written. Add --apply to reverse.")
        print("NOTE: collapse reversal does NOT restore inbound-FK repoints / DedupeResolution.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Held-listings final op (dry-run default).")
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    ap.add_argument("--undo-csv", default="undo_held_listings_2026-07-05.csv")
    ap.add_argument("--reactivate-from", dest="undo_in", help="undo CSV to reverse a prior apply")
    args = ap.parse_args(argv)
    if args.undo_in:
        return reactivate(args.undo_in, args.apply)
    return run(args.apply, args.undo_csv)


if __name__ == "__main__":
    raise SystemExit(main())
