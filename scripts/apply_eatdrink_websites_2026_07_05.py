"""Session 6d Phase 2 — Eat & Drink website backfill (GATED, dry-run default).

Input: docs/audits/2026-07/completeness_eatdrink_websites_filled_2026-07-05.csv
(Casey's hand-filled proposals from the Phase-1 gaps CSV). One row = one listing.

Only rows whose ``action == "apply"`` are written. For each, set the listing's
website to ``proposed_website`` — but ONLY if it is CURRENTLY EMPTY. The website
surface is ``Provider.website`` for a provider-backed listing, or a ``website``
ContactPoint for a place. A listing that already carries any website value, or
that is protected (verified / claimed / sponsored), is SKIPPED and reported —
we never overwrite or auto-edit an owner-controlled listing.

Special case: entity 246ff9ad "Lina Little China" also gets its Entity.name
corrected to "Lin's Little China" (per the CSV note).

Rows with action in {review, flag-review, flag-junk, flag-miscat, flag-dup} are
NOT touched here — they are listed for Casey (junk removal / miscat / dup collapse
/ verification are separate ops).

Each proposed URL is validated (http/https scheme + dotted host) before it can be
written; malformed URLs are reported as validation failures and skipped.

Reversible: ``--apply`` writes ONE transaction + an undo CSV; reverse with
``--reactivate-from <undo.csv> --apply``.

PROD GATE (CLAUDE.md): dry-run -> paste counts -> Casey approves -> apply.

    .venv\\Scripts\\python.exe scripts/apply_eatdrink_websites_2026_07_05.py
    .venv\\Scripts\\python.exe scripts/apply_eatdrink_websites_2026_07_05.py --apply --undo-csv undo_eatdrink_websites_2026-07-05.csv
    .venv\\Scripts\\python.exe scripts/apply_eatdrink_websites_2026_07_05.py --reactivate-from undo_eatdrink_websites_2026-07-05.csv --apply
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Claim, ContactPoint, Entity, Provider  # noqa: E402

_FILLED_DEFAULT = (
    _ROOT / "docs" / "audits" / "2026-07"
    / "completeness_eatdrink_websites_filled_2026-07-05.csv"
)

_WEB_KINDS = {"website", "web", "url"}

# Name-fix special case (per CSV note).
_NAME_FIX = {"246ff9ad-a0bc-462e-941e-87446b3c781b": ("Lina Little China", "Lin's Little China")}

# Actions that are NOT applied here — listed for Casey.
_FLAG_ACTIONS = {"review", "flag-review", "flag-junk", "flag-miscat", "flag-dup"}


def _valid_url(u: str) -> bool:
    """Well-formed http(s) URL with a dotted host."""
    try:
        p = urlparse((u or "").strip())
    except (ValueError, TypeError):
        return False
    return p.scheme in ("http", "https") and bool(p.netloc) and "." in p.netloc


def _is_sponsored(p: Provider, now: datetime) -> bool:
    tier = (getattr(p, "tier", "") or "").strip()
    if tier not in ("", "free"):
        return True
    su = p.sponsored_until
    if su is not None:
        if su.tzinfo is None:
            su = su.replace(tzinfo=UTC)
        if su > now:
            return True
    return False


def _web_cp(cps: list[ContactPoint]) -> ContactPoint | None:
    for cp in cps:
        if (cp.kind or "").strip().lower() in _WEB_KINDS and (cp.value or "").strip():
            return cp
    return None


@dataclass
class Plan:
    entity_id: str
    name: str
    action: str                 # set-website | skip | flag
    detail: str = ""
    skip_reason: str = ""
    flag_kind: str = ""
    # write targets
    target: str = ""            # provider | contact_point
    provider_id: str = ""
    prior_website: str = ""     # for undo (provider path)
    proposed_website: str = ""
    name_fix_from: str = ""
    name_fix_to: str = ""


def _build_plans(db) -> tuple[list[Plan], list[str]]:
    now = datetime.now(UTC)
    warnings: list[str] = []

    claimed = {r[0] for r in db.query(Claim.entity_id).filter(Claim.status == "verified").all()}

    plans: list[Plan] = []
    with open(_FILLED_DEFAULT, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            eid = (r.get("entity_id") or "").strip()
            name = (r.get("name") or "").strip()
            proposed = (r.get("proposed_website") or "").strip()
            action = (r.get("action") or "").strip().lower()

            if action in _FLAG_ACTIONS:
                plans.append(Plan(eid, name, "flag", flag_kind=action, detail=(r.get("note") or "").strip()))
                continue
            if action != "apply":
                plans.append(Plan(eid, name, "skip", skip_reason=f"unknown action {action!r}"))
                continue

            ent = db.get(Entity, eid)
            if ent is None:
                plans.append(Plan(eid, name, "skip", skip_reason="entity not found"))
                continue
            if (ent.name or "").strip().lower() != name.lower() and eid not in _NAME_FIX:
                warnings.append(f"name mismatch: CSV {name!r} vs DB {ent.name!r} ({eid[:8]})")

            if not proposed:
                plans.append(Plan(eid, name, "skip", skip_reason="apply row with empty proposed_website"))
                continue
            if not _valid_url(proposed):
                plans.append(Plan(eid, name, "skip", skip_reason=f"malformed URL: {proposed!r}"))
                continue

            provs = [p for p in db.query(Provider).filter(Provider.entity_id == eid).all()]
            active_provs = [p for p in provs if p.is_active and not p.draft]
            cps = db.query(ContactPoint).filter(ContactPoint.entity_id == eid).all()

            # protected? (verified / claimed / sponsored) → never auto-edit.
            prot = None
            if eid in claimed:
                prot = "claimed"
            else:
                for p in provs:
                    if p.verified:
                        prot = "verified"
                        break
                    if _is_sponsored(p, now):
                        prot = "sponsored"
                        break

            # current website value (Provider.website or a web ContactPoint)
            cur_prov_web = next((p.website.strip() for p in active_provs if (p.website or "").strip()), "")
            cur_cp = _web_cp(cps)
            current = cur_prov_web or (cur_cp.value.strip() if cur_cp else "")

            name_from = name_to = ""
            if eid in _NAME_FIX:
                name_from, name_to = _NAME_FIX[eid]

            if current:
                plans.append(Plan(eid, name, "skip", skip_reason="already has a website",
                                  detail=f"current={current}", proposed_website=proposed))
                continue
            if prot is not None:
                plans.append(Plan(eid, name, "skip", skip_reason=f"protected: {prot}",
                                  proposed_website=proposed))
                continue

            # choose write target: prefer the provider surface if provider-backed.
            if active_provs:
                # write to the highest-review active provider (the card's row)
                target_p = sorted(active_provs, key=lambda p: -(getattr(p, "google_review_count", 0) or 0))[0]
                plans.append(Plan(
                    eid, name, "set-website",
                    detail=f"Provider.website ← {proposed}"
                           + (f"  +NAME '{name_from}'→'{name_to}'" if name_to else ""),
                    target="provider", provider_id=target_p.id,
                    prior_website=(target_p.website or ""), proposed_website=proposed,
                    name_fix_from=name_from, name_fix_to=name_to,
                ))
            else:
                plans.append(Plan(
                    eid, name, "set-website",
                    detail=f"new website ContactPoint ← {proposed}"
                           + (f"  +NAME '{name_from}'→'{name_to}'" if name_to else ""),
                    target="contact_point", proposed_website=proposed,
                    name_fix_from=name_from, name_fix_to=name_to,
                ))
    return plans, warnings


_UNDO_FIELDS = ["op", "entity_id", "name", "target", "provider_id", "prior_website",
                "new_website", "name_fix_from", "name_fix_to"]


def _apply_plan(db, pl: Plan) -> dict:
    """Write one set-website plan; return its undo row."""
    if pl.target == "provider":
        p = db.get(Provider, pl.provider_id)
        if p is not None:
            p.website = pl.proposed_website
    else:  # contact_point
        db.add(ContactPoint(entity_id=pl.entity_id, kind="website",
                            value=pl.proposed_website, is_primary=True, display_order=0))
    if pl.name_fix_to:
        ent = db.get(Entity, pl.entity_id)
        if ent is not None:
            ent.name = pl.name_fix_to
    return {
        "op": "set-website", "entity_id": pl.entity_id, "name": pl.name,
        "target": pl.target, "provider_id": pl.provider_id,
        "prior_website": pl.prior_website, "new_website": pl.proposed_website,
        "name_fix_from": pl.name_fix_from, "name_fix_to": pl.name_fix_to,
    }


def run(apply: bool, undo_csv: str | None) -> int:
    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    with SessionLocal() as db:
        plans, warnings = _build_plans(db)

        setw = [p for p in plans if p.action == "set-website"]
        skips = [p for p in plans if p.action == "skip"]
        flags = [p for p in plans if p.action == "flag"]

        mode = "APPLY (writing)" if apply else "DRY RUN (no writes)"
        print("=" * 86)
        print(f"EAT & DRINK WEBSITE BACKFILL — Session 6d Phase 2 — {mode}")
        print("=" * 86)
        print(f"DB target: …@{redacted}")
        print(f"rows: {len(plans)}   set-website: {len(setw)}   skip: {len(skips)}   flag: {len(flags)}\n")
        for w in warnings:
            print(f"  ! {w}")
        if warnings:
            print()

        print(f"--- WOULD SET WEBSITE ({len(setw)}) ---")
        for pl in sorted(setw, key=lambda p: p.name.lower()):
            print(f"  {pl.name[:40]:40s} [{pl.target:12s}] {pl.detail}")

        print(f"\n--- SKIPPED ({len(skips)}) ---")
        skip_by_reason: dict[str, list[Plan]] = {}
        for pl in skips:
            skip_by_reason.setdefault(pl.skip_reason, []).append(pl)
        for reason, rows in sorted(skip_by_reason.items(), key=lambda kv: -len(kv[1])):
            print(f"  [{len(rows)}] {reason}")
            for pl in rows:
                extra = f"  ({pl.detail})" if pl.detail else ""
                print(f"        {pl.name[:48]:48s}{extra}")

        # validation-failure highlight
        val_fail = [pl for pl in skips if any(
            k in pl.skip_reason for k in ("malformed URL", "entity not found", "empty proposed_website"))]
        if val_fail:
            print(f"\n!! VALIDATION FAILURES ({len(val_fail)}):")
            for pl in val_fail:
                print(f"     {pl.name[:44]:44s} — {pl.skip_reason}")

        # flag summary (for Casey — NOT applied here)
        print(f"\n--- FLAGGED FOR CASEY (not touched in this op) ({len(flags)}) ---")
        flag_by_kind: dict[str, list[Plan]] = {}
        for pl in flags:
            flag_by_kind.setdefault(pl.flag_kind, []).append(pl)
        for kind in ("flag-junk", "flag-miscat", "flag-dup", "flag-review", "review"):
            rows = flag_by_kind.get(kind, [])
            if not rows:
                continue
            print(f"  {kind} ({len(rows)}):")
            for pl in rows:
                print(f"        {pl.name[:44]:44s} {pl.detail[:64]}")

        if not apply:
            print("\nDRY RUN — nothing written. After approval, re-run with --apply --undo-csv <path>.")
            return 0

        undo_rows = [_apply_plan(db, pl) for pl in setw]
        if undo_csv:
            with open(undo_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=_UNDO_FIELDS)
                w.writeheader()
                w.writerows(undo_rows)
        db.commit()
        print(f"\nAPPLIED: set-website={len(setw)}. Undo: {undo_csv}")
        return 0


def reactivate(undo_csv: str, apply: bool) -> int:
    with SessionLocal() as db:
        n = Counter()
        for r in csv.DictReader(open(undo_csv, newline="", encoding="utf-8")):
            if r.get("op") != "set-website":
                continue
            if r.get("target") == "provider":
                p = db.get(Provider, r["provider_id"]) if r.get("provider_id") else None
                if p is not None and apply:
                    p.website = r.get("prior_website") or None
            else:
                # delete the website CP we created (match entity + value)
                if apply:
                    db.query(ContactPoint).filter(
                        ContactPoint.entity_id == r["entity_id"],
                        ContactPoint.kind == "website",
                        ContactPoint.value == r.get("new_website"),
                    ).delete()
            if r.get("name_fix_to"):
                ent = db.get(Entity, r["entity_id"])
                if ent is not None and apply and r.get("name_fix_from"):
                    ent.name = r["name_fix_from"]
            n["set-website"] += 1
        if apply:
            db.commit()
        verb = "REVERSED" if apply else "would reverse"
        print(f"{verb}: set-website={n['set-website']}")
        if not apply:
            print("DRY RUN: nothing written. Add --apply to reverse.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Apply Eat & Drink website backfill (dry-run default).")
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    ap.add_argument("--undo-csv", default="undo_eatdrink_websites_2026-07-05.csv")
    ap.add_argument("--reactivate-from", dest="undo_in", help="undo CSV to reverse a prior apply")
    args = ap.parse_args(argv)
    if args.undo_in:
        return reactivate(args.undo_in, args.apply)
    return run(args.apply, args.undo_csv)


if __name__ == "__main__":
    raise SystemExit(main())
