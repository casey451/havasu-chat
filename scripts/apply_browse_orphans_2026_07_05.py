"""Session 6a Phase 2 — apply the confirmed browse-orphans review (GATED, dry-run default).

Drives three reversible ops from Casey's confirmed review CSV, one row = one action:

  * REPOINT  (bucket A, non-empty proposed_leaf, flag != 'review') — swap the
    entity's PRIMARY ``EntityCategory`` onto the proposed leaf (swap onto an
    existing target link if present, else rewrite the primary row's
    ``category_id``). Mirrors ``recategorize_lodging_misfiles_2026_07_05.py``.
  * DEACTIVATE (bucket B flagged 'deactivate', or a bucket-A straggler whose note
    begins 'DEACTIVATE') — ``Entity.is_active=False`` + cascade every
    ``Provider.is_active=False``. Mirrors ``deactivate_places_to_stay_2026_07_05``
    / ``apply_bogus_deactivation``.
  * COLLAPSE (bucket C flagged 'collapse') — fold the orphan into its canonical
    twin via ``app.contrib.provider_merge.merge_providers`` (gap-fill the
    survivor's empty scalars from the orphan, repoint inbound FKs, soft-retire the
    orphan provider + its Entity, 301 redirect). The 3D/Op1 "merge richest onto
    survivor, then deactivate the orphan" pattern.

Anything with an empty ``proposed_leaf`` / flag 'review' and no confirmed action
is SKIPPED and listed as **unresolved** (no guessing).

SOURCE-OF-TRUTH JOIN: entity_id + twin_of come from the ORIGINAL enumerator CSV
(``--original``); Casey's decisions come from the hand-edited ``--filled`` CSV.
Rows are joined on entity_id; a filled entity_id absent from the original is
recovered by unique provider_name match (the original wins — the filled IDs were
hand-transcribed).

Apply-time skip guards (re-checked live, mirroring apply_bogus_deactivation):
verified / claimed (Claim.status=='verified') / sponsored / already-done rows are
skipped for the DESTRUCTIVE ops (deactivate, collapse). Repoint is corrective /
non-destructive, so it only skips already-at-target and invalid-leaf rows (a
verified row still gets repointed to its correct leaf — it should be visible); any
protected repoint targets are reported for visibility, not skipped.

Reversible: ``--apply`` writes ONE transaction + an undo CSV; reverse with
``--reactivate-from <undo.csv> --apply``. Collapse reversal is best-effort
("reversible-ish", same caveat as every prior merge): it reactivates the orphan +
un-retires the dup provider + strips the redirect + clears the survivor scalars we
gap-filled, but does NOT walk back the inbound-FK repoints or the DedupeResolution
row.

PROD GATE (CLAUDE.md): dry-run -> paste counts -> Casey approves -> apply.

    .venv\\Scripts\\python.exe -m scripts.apply_browse_orphans_2026_07_05
    .venv\\Scripts\\python.exe -m scripts.apply_browse_orphans_2026_07_05 --apply --undo-csv undo_browse_orphans_2026-07-05.csv
    .venv\\Scripts\\python.exe -m scripts.apply_browse_orphans_2026_07_05 --reactivate-from undo_browse_orphans_2026-07-05.csv --apply
"""

from __future__ import annotations

import argparse
import csv
import json
import re
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

from app.categories.leaf_pages import _gate_counts  # noqa: E402
from app.contrib.provider_merge import merge_providers  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, Claim, Entity, EntityCategory, Provider  # noqa: E402

_ORIGINAL_DEFAULT = _ROOT / "docs" / "audits" / "2026-07" / "browse_orphans_review_2026-07-05.csv"
_FILLED_DEFAULT = _ROOT / "docs" / "audits" / "2026-07" / "browse_orphans_review_2026-07-05_filled.csv"

# ---- name normalization (matches the Phase-1 enumerator) -------------------
_NAME_SUFFIX_RE = re.compile(
    r"\b(llc|l\.l\.c|inc|incorporated|co|corp|corporation|company|ltd|lp|"
    r"pllc|pc|the|and|&)\b"
)
_NAME_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
_WS_RE = re.compile(r"\s+")


def _norm_name(name: str | None) -> str:
    s = (name or "").lower()
    s = _NAME_PUNCT_RE.sub(" ", s)
    s = _NAME_SUFFIX_RE.sub(" ", s)
    return _WS_RE.sub(" ", s).strip()


# ---- decision model --------------------------------------------------------
@dataclass
class Decision:
    entity_id: str            # authoritative (original wins)
    name: str
    bucket: str
    cause: str
    action: str               # repoint | deactivate | collapse | unresolved
    proposed_leaf: str = ""
    twin_of: str = ""
    note: str = ""
    id_recovered: bool = False
    unresolved_reason: str = ""


def _load_decisions(original_csv: Path, filled_csv: Path) -> tuple[list[Decision], list[str]]:
    """Join filled decisions onto the original (source of truth for id + twin_of)."""
    original = {
        r["entity_id"]: r
        for r in csv.DictReader(open(original_csv, newline="", encoding="utf-8"))
    }
    orig_by_name: dict[str, list[dict]] = {}
    for r in original.values():
        orig_by_name.setdefault(_norm_name(r["provider_name"]), []).append(r)

    decisions: list[Decision] = []
    warnings: list[str] = []
    for r in csv.DictReader(open(filled_csv, newline="", encoding="utf-8")):
        fid = (r.get("entity_id") or "").strip()
        name = (r.get("provider_name") or "").strip()
        bucket = (r.get("bucket") or "").strip().upper()
        cause = (r.get("cause") or "").strip().lower()
        proposed = (r.get("proposed_leaf") or "").strip()
        flag = (r.get("confidence") or "").strip().lower()
        note = (r.get("note") or "").strip()

        id_recovered = False
        orig = original.get(fid)
        if orig is None:
            cands = orig_by_name.get(_norm_name(name), [])
            if len(cands) == 1:
                orig = cands[0]
                fid = orig["entity_id"]
                id_recovered = True
                warnings.append(f"id recovered by name: {name} -> {fid}")
            else:
                decisions.append(Decision(
                    entity_id=fid, name=name, bucket=bucket, cause=cause,
                    action="unresolved", proposed_leaf=proposed, note=note,
                    unresolved_reason="filled entity_id not in original and name not unique",
                ))
                continue
        twin_of = (orig.get("twin_of") or "").strip()

        # ---- resolve the action ----
        action = "unresolved"
        reason = ""
        if bucket == "C":
            if flag == "collapse":
                action = "collapse"
            else:
                reason = f"bucket C flag={flag or '(blank)'} (not 'collapse')"
        elif bucket == "B":
            if flag == "deactivate":
                action = "deactivate"
            else:
                reason = f"bucket B flag={flag or '(blank)'} (not 'deactivate')"
        elif bucket == "A":
            if note.upper().startswith("DEACTIVATE"):
                action = "deactivate"
            elif proposed and flag != "review":
                action = "repoint"
            else:
                reason = (
                    "empty proposed_leaf" if not proposed
                    else f"flag={flag or '(blank)'}"
                )
        else:
            reason = f"unknown bucket {bucket!r}"

        decisions.append(Decision(
            entity_id=fid, name=name, bucket=bucket, cause=cause, action=action,
            proposed_leaf=proposed, twin_of=twin_of, note=note,
            id_recovered=id_recovered, unresolved_reason=reason,
        ))
    return decisions, warnings


# ---- live-DB helpers -------------------------------------------------------
def _is_sponsored(p: Provider, now: datetime) -> bool:
    tier = (p.tier or "").strip()
    if tier not in ("", "free"):
        return True
    su = p.sponsored_until
    if su is not None:
        if su.tzinfo is None:
            su = su.replace(tzinfo=UTC)
        if su > now:
            return True
    return False


def _protected_reason(ent: Entity, provs: list[Provider], claimed: set[str], now: datetime) -> str | None:
    if ent.id in claimed:
        return "claimed"
    for p in provs:
        if p.verified:
            return "verified"
        if _is_sponsored(p, now):
            return "sponsored"
    return None


def _primary_ec(db, entity_id: str) -> EntityCategory | None:
    return (
        db.query(EntityCategory)
        .filter(EntityCategory.entity_id == entity_id, EntityCategory.is_primary.is_(True))
        .first()
    )


def _primary_provider(provs: list[Provider]) -> Provider | None:
    if not provs:
        return None
    return sorted(provs, key=lambda p: -(p.google_review_count or 0))[0]


@dataclass
class Plan:
    decision: Decision
    action: str                    # repoint | deactivate | collapse | skip
    detail: str = ""               # human summary
    skip_reason: str = ""
    # repoint
    prim_ec_id: int | None = None
    old_category_id: int | None = None
    old_slug: str = ""
    target_ec_id: int | None = None
    new_category_id: int | None = None
    new_slug: str = ""
    mode: str = ""                 # swap | repoint
    # deactivate / collapse
    provider_ids: list[str] = field(default_factory=list)
    survivor_entity_id: str = ""
    keep_provider_id: str = ""
    dup_provider_id: str = ""
    gap_filled: list[str] = field(default_factory=list)
    dup_prior: dict = field(default_factory=dict)


def _build_plans(db, decisions: list[Decision]) -> list[Plan]:
    now = datetime.now(UTC)
    cats_by_slug = {c.slug: c for c in db.query(Category).all()}
    leaf_slugs = {s for s, c in cats_by_slug.items() if c.level == 1}
    shipping = set(_gate_counts(db).keys())
    claimed = {r[0] for r in db.query(Claim.entity_id).filter(Claim.status == "verified").all()}

    # provider index for every active entity (survivor resolution + cascades)
    provs_by_entity: dict[str, list[Provider]] = {}
    for p in db.query(Provider).all():
        provs_by_entity.setdefault(p.entity_id, []).append(p)
    # active provider-backed entities keyed by normalized name (survivor lookup)
    active_names: dict[str, list[Entity]] = {}
    for e in db.query(Entity).filter(Entity.is_active.is_(True)).all():
        if provs_by_entity.get(e.id):
            active_names.setdefault(_norm_name(e.name), []).append(e)

    def _slug_of(cid) -> str:
        c = db.get(Category, cid)
        return c.slug if c else str(cid)

    plans: list[Plan] = []
    for d in decisions:
        if d.action == "unresolved":
            plans.append(Plan(d, "skip", skip_reason=d.unresolved_reason or "unresolved"))
            continue

        ent = db.get(Entity, d.entity_id)
        if ent is None:
            plans.append(Plan(d, "skip", skip_reason="entity not found"))
            continue
        provs = provs_by_entity.get(ent.id, [])

        # -------- REPOINT --------
        if d.action == "repoint":
            target = cats_by_slug.get(d.proposed_leaf)
            if target is None or d.proposed_leaf not in leaf_slugs:
                plans.append(Plan(d, "skip",
                                  skip_reason=f"proposed_leaf '{d.proposed_leaf}' is not a live level-1 leaf"))
                continue
            if not ent.is_active:
                plans.append(Plan(d, "skip", skip_reason="entity already inactive"))
                continue
            prim = _primary_ec(db, ent.id)
            if prim is not None and prim.category_id == target.id:
                plans.append(Plan(d, "skip", skip_reason="already at target leaf"))
                continue
            # An existing (entity, target) link — primary OR secondary — regardless
            # of whether a primary exists elsewhere.
            existing = (
                db.query(EntityCategory)
                .filter(EntityCategory.entity_id == ent.id,
                        EntityCategory.category_id == target.id)
                .one_or_none()
            )
            # Four modes: swap (move primary off another link onto an existing
            # target link), promote (no primary today, target link exists),
            # repoint (rewrite the existing primary row's category_id), insert
            # (cause-a: no primary and no target link — create one).
            if existing is not None and prim is not None and existing.id != prim.id:
                mode = "swap"
            elif existing is not None and prim is None:
                mode = "promote"
            elif prim is not None:
                mode = "repoint"
            else:
                mode = "insert"
            prot = _protected_reason(ent, provs, claimed, now)
            note = f"  [protected:{prot} — repointed anyway (corrective)]" if prot else ""
            gate = "" if (target.id in shipping) else "  [target currently below gate]"
            old_slug = _slug_of(prim.category_id) if prim else "(none)"
            plans.append(Plan(
                d, "repoint",
                detail=f"{old_slug} -> {target.slug} [{mode}]{note}{gate}",
                prim_ec_id=(prim.id if prim else None),
                old_category_id=(prim.category_id if prim else None),
                old_slug=(_slug_of(prim.category_id) if prim else ""),
                target_ec_id=(existing.id if existing is not None else None),
                new_category_id=target.id, new_slug=target.slug, mode=mode,
            ))
            continue

        # -------- DEACTIVATE --------
        if d.action == "deactivate":
            if not ent.is_active:
                plans.append(Plan(d, "skip", skip_reason="already inactive"))
                continue
            prot = _protected_reason(ent, provs, claimed, now)
            if prot is not None:
                plans.append(Plan(d, "skip", skip_reason=f"protected: {prot}"))
                continue
            plans.append(Plan(
                d, "deactivate",
                detail=f"deactivate + cascade {len(provs)} provider(s)",
                provider_ids=[p.id for p in provs],
            ))
            continue

        # -------- COLLAPSE --------
        if d.action == "collapse":
            prot = _protected_reason(ent, provs, claimed, now)
            if prot is not None:
                plans.append(Plan(d, "skip", skip_reason=f"protected: {prot}"))
                continue
            # resolve survivor by twin_of (active, provider-backed, != orphan)
            cands = [e for e in active_names.get(_norm_name(d.twin_of), []) if e.id != ent.id]
            if len(cands) > 1:
                shipping_cands = [
                    e for e in cands
                    if (pe := _primary_ec(db, e.id)) is not None and pe.category_id in shipping
                ]
                cands = shipping_cands or cands
            if len(cands) != 1:
                plans.append(Plan(d, "skip",
                                  skip_reason=f"survivor '{d.twin_of}' resolved to {len(cands)} candidates"))
                continue
            survivor = cands[0]
            dup_prov = _primary_provider(provs)
            keep_prov = _primary_provider(provs_by_entity.get(survivor.id, []))
            if dup_prov is None or keep_prov is None:
                plans.append(Plan(d, "skip",
                                  skip_reason="orphan or survivor is not provider-backed (can't merge)"))
                continue
            if (dup_prov.source or "").strip() == "operator":
                plans.append(Plan(d, "skip", skip_reason="orphan provider is operator-sourced"))
                continue
            try:
                mr = merge_providers(db, keep_id=keep_prov.id, dup_id=dup_prov.id, dry_run=True)
            except ValueError as exc:
                plans.append(Plan(d, "skip", skip_reason=f"merge refused: {exc}"))
                continue
            other = [p.id for p in provs if p.id != dup_prov.id]
            plans.append(Plan(
                d, "collapse",
                detail=f"into '{survivor.name}'  gap_fill={mr.gap_filled or '-'}  "
                       f"repoint={mr.repointed or '-'}"
                       + (f"  +{len(other)} other orphan provider(s) cascaded" if other else ""),
                survivor_entity_id=survivor.id,
                keep_provider_id=keep_prov.id, dup_provider_id=dup_prov.id,
                provider_ids=other, gap_filled=list(mr.gap_filled),
                dup_prior={
                    "is_active": bool(dup_prov.is_active), "draft": bool(dup_prov.draft),
                    "pending_review": bool(dup_prov.pending_review),
                    "had_redirect": bool((dup_prov.attributes or {}).get("merged_into_slug")),
                },
            ))
            continue

        plans.append(Plan(d, "skip", skip_reason=f"unhandled action {d.action}"))
    return plans


# ---- apply -----------------------------------------------------------------
def _apply_plan(db, pl: Plan) -> None:
    if pl.action == "repoint":
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
            db.add(EntityCategory(
                entity_id=pl.decision.entity_id,
                category_id=pl.new_category_id,
                is_primary=True,
            ))
    elif pl.action == "deactivate":
        ent = db.get(Entity, pl.decision.entity_id)
        if ent is not None:
            ent.is_active = False
        for pid in pl.provider_ids:
            p = db.get(Provider, pid)
            if p is not None and p.is_active:
                p.is_active = False
    elif pl.action == "collapse":
        merge_providers(db, keep_id=pl.keep_provider_id, dup_id=pl.dup_provider_id, dry_run=False)
        # cascade any OTHER providers on the orphan entity (merge only retired the primary)
        for pid in pl.provider_ids:
            p = db.get(Provider, pid)
            if p is not None and p.is_active:
                p.is_active = False


_UNDO_FIELDS = [
    "op", "entity_id", "name", "prim_ec_id", "old_category_id", "target_ec_id",
    "new_category_id", "mode", "provider_ids", "survivor_entity_id",
    "keep_provider_id", "dup_provider_id", "extra_json",
]


def _undo_row(pl: Plan) -> dict:
    d = pl.decision
    row = {k: "" for k in _UNDO_FIELDS}
    row.update(op=pl.action, entity_id=d.entity_id, name=d.name)
    if pl.action == "repoint":
        row.update(prim_ec_id=pl.prim_ec_id or "", old_category_id=pl.old_category_id or "",
                   target_ec_id=pl.target_ec_id or "", new_category_id=pl.new_category_id or "",
                   mode=pl.mode)
    elif pl.action == "deactivate":
        row.update(provider_ids=";".join(pl.provider_ids))
    elif pl.action == "collapse":
        row.update(provider_ids=";".join(pl.provider_ids),
                   survivor_entity_id=pl.survivor_entity_id,
                   keep_provider_id=pl.keep_provider_id, dup_provider_id=pl.dup_provider_id,
                   extra_json=json.dumps({"gap_filled": pl.gap_filled, "dup_prior": pl.dup_prior}))
    return row


def run(filled: Path, original: Path, apply: bool, undo_csv: str | None) -> int:
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    decisions, warnings = _load_decisions(original, filled)
    with SessionLocal() as db:
        plans = _build_plans(db, decisions)

        mode = "APPLY (writing)" if apply else "DRY RUN (no writes)"
        print("=" * 84)
        print(f"BROWSE-ORPHANS APPLY — Session 6a Phase 2 — {mode}")
        print("=" * 84)
        print(f"DB target: …@{redacted}")
        print(f"decisions: {len(decisions)}  (filled rows joined to original)\n")
        for w in warnings:
            print(f"  note: {w}")
        if warnings:
            print()

        by_action: dict[str, list[Plan]] = {"repoint": [], "deactivate": [], "collapse": [], "skip": []}
        for pl in plans:
            by_action[pl.action].append(pl)

        print("PER-ACTION COUNTS:")
        print(f"  REPOINT (bucket A):        {len(by_action['repoint'])}")
        print(f"  DEACTIVATE (bucket B + A straggler): {len(by_action['deactivate'])}")
        print(f"  COLLAPSE (bucket C):       {len(by_action['collapse'])}")
        print(f"  SKIPPED / unresolved:      {len(by_action['skip'])}")

        def _dump(action: str, label: str) -> None:
            rows = by_action[action]
            print(f"\n--- {label} ({len(rows)}) ---")
            for pl in sorted(rows, key=lambda p: p.decision.name.lower()):
                print(f"    {pl.decision.name[:44]:44s} {pl.detail}")

        _dump("repoint", "REPOINT → proposed leaf")
        _dump("deactivate", "DEACTIVATE (Entity.is_active=False + cascade providers)")
        _dump("collapse", "COLLAPSE into canonical twin (merge_providers)")

        # skipped, grouped by reason
        print(f"\n--- SKIPPED / UNRESOLVED ({len(by_action['skip'])}) ---")
        skip_by_reason: dict[str, list[Plan]] = {}
        for pl in by_action["skip"]:
            skip_by_reason.setdefault(pl.skip_reason, []).append(pl)
        for reason, rows in sorted(skip_by_reason.items(), key=lambda kv: -len(kv[1])):
            print(f"  [{len(rows)}] {reason}")
            for pl in rows:
                print(f"        {pl.decision.name[:56]}")

        # validation-failure highlight (bad leaf slug / survivor / not-found)
        val_fail = [pl for pl in by_action["skip"] if any(
            k in pl.skip_reason for k in ("not a live level-1 leaf", "survivor", "not found",
                                          "not provider-backed", "not in original"))]
        if val_fail:
            print(f"\n!! VALIDATION FAILURES (need Casey / a fix): {len(val_fail)}")
            for pl in val_fail:
                print(f"     {pl.decision.name[:48]:48s} — {pl.skip_reason}")

        if not apply:
            print("\nDRY RUN — nothing written. After approval, re-run with "
                  "--apply --undo-csv <path>.")
            return 0

        # ---- write (one transaction) ----
        actionable = by_action["repoint"] + by_action["deactivate"] + by_action["collapse"]
        undo_rows = [_undo_row(pl) for pl in actionable]
        for pl in actionable:
            _apply_plan(db, pl)
        if undo_csv:
            with open(undo_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=_UNDO_FIELDS)
                w.writeheader()
                w.writerows(undo_rows)
        db.commit()
        print(f"\nAPPLIED: repoint={len(by_action['repoint'])} "
              f"deactivate={len(by_action['deactivate'])} "
              f"collapse={len(by_action['collapse'])}. Undo: {undo_csv}")
        return 0


def reactivate(undo_csv: str, apply: bool) -> int:
    with SessionLocal() as db:
        n = Counter()
        for r in csv.DictReader(open(undo_csv, newline="", encoding="utf-8")):
            op = r.get("op")
            if op == "repoint":
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
                            EntityCategory.category_id == int(r["new_category_id"]),
                        ).delete()
                n["repoint"] += 1
            elif op == "deactivate":
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
                # reactivate orphan entity + its providers
                ent = db.get(Entity, r["entity_id"])
                if ent is not None and apply:
                    ent.is_active = True
                dup = db.get(Provider, r["dup_provider_id"]) if r.get("dup_provider_id") else None
                if dup is not None and apply:
                    dup.is_active = prior.get("is_active", True)
                    dup.draft = prior.get("draft", False)
                    dup.pending_review = prior.get("pending_review", False)
                    if not prior.get("had_redirect") and dup.attributes:
                        attrs = dict(dup.attributes)
                        attrs.pop("merged_into_slug", None)
                        dup.attributes = attrs
                for pid in (r.get("provider_ids") or "").split(";"):
                    if pid.strip() and apply:
                        p = db.get(Provider, pid.strip())
                        if p is not None:
                            p.is_active = True
                # clear the scalars we gap-filled onto the survivor
                keep = db.get(Provider, r["keep_provider_id"]) if r.get("keep_provider_id") else None
                if keep is not None and apply:
                    for fld in extra.get("gap_filled", []):
                        setattr(keep, fld, None)
                n["collapse"] += 1
        if apply:
            db.commit()
        verb = "REVERSED" if apply else "would reverse"
        print(f"{verb}: repoint={n['repoint']} deactivate={n['deactivate']} collapse={n['collapse']}")
        if not apply:
            print("DRY RUN: nothing written. Add --apply to reverse.")
        print("NOTE: collapse reversal does NOT restore inbound-FK repoints or the "
              "DedupeResolution row (reversible-ish, per merge_providers).")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Apply confirmed browse-orphans review (dry-run default).")
    ap.add_argument("--filled", type=Path, default=_FILLED_DEFAULT,
                    help="Casey's confirmed review CSV")
    ap.add_argument("--original", type=Path, default=_ORIGINAL_DEFAULT,
                    help="original enumerator CSV (source of truth for entity_id + twin_of)")
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    ap.add_argument("--undo-csv", default="undo_browse_orphans_2026-07-05.csv")
    ap.add_argument("--reactivate-from", dest="undo_in", help="undo CSV to reverse a prior apply")
    args = ap.parse_args(argv)
    if args.undo_in:
        return reactivate(args.undo_in, args.apply)
    return run(args.filled, args.original, args.apply, args.undo_csv)


if __name__ == "__main__":
    raise SystemExit(main())
