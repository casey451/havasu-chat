"""READ-ONLY practitioner-vs-practice cluster report (search round-2 N3b).

The "N Best X" counts for dentists (53), eye care (19), and real estate (60)
are inflated because individual practitioners are listed separately from — and
often at the same address as — their practice. This groups each leaf's
PRIMARY-linked active entities by normalized street address, flags multi-row
clusters, and marks each row as a likely PRACTICE or likely INDIVIDUAL (by
name shape: personal-name + credential suffix → individual).

Writes nothing. Output is the input to a Casey-reviewed demote plan (demote the
individual rows at a practice's address to non-primary → drops them from the
count while keeping the listing). Run against prod.

Usage:
    .venv\\Scripts\\python.exe scripts/audit_practitioner_clusters_2026_07_01.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Category, Entity, EntityCategory, Location, Provider  # noqa: E402

_LEAVES = ("dentists-and-orthodontists", "eye-care", "real-estate")

# Credential / individual-practitioner name signals.
_CRED_RE = re.compile(
    r"\b(d\.?d\.?s|d\.?m\.?d|o\.?d|m\.?d|dds|dmd|realtor|"
    r"broker|agent|associate|p\.?c)\b",
    re.I,
)
# A "First Last" personal-name shape (two capitalized words, not an org word).
_ORG_WORDS = re.compile(
    r"\b(clinic|center|centre|group|associates|family|dental|vision|eye|"
    r"orthodont|realty|real estate|properties|company|co|inc|llc|team|"
    r"office|care|spa|labs?|prosthetic)\b",
    re.I,
)


def _norm_addr(raw: str | None) -> str:
    s = (raw or "").split(",")[0].strip().lower()
    s = re.sub(r"\b(suite|ste|unit|#|apt)\b.*$", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _addr_for(db, eid: str) -> str:
    p = db.query(Provider).filter_by(entity_id=eid).first()
    if p and p.address:
        return p.address
    loc = db.query(Location).filter_by(entity_id=eid).first()
    return (loc.address_line1 or "") if loc else ""


def _kind(name: str) -> str:
    """PRACTICE vs INDIVIDUAL vs ? (heuristic, for review only)."""
    has_cred = bool(_CRED_RE.search(name))
    has_org = bool(_ORG_WORDS.search(name))
    if has_cred and not has_org:
        return "INDIVIDUAL"
    if has_org and not has_cred:
        return "PRACTICE"
    if has_cred and has_org:
        return "INDIVIDUAL?"  # e.g. "Jane Doe DDS at Smile Center"
    return "?"


def main() -> int:
    with SessionLocal() as db:
        print("=" * 74)
        print("PRACTITIONER-vs-PRACTICE CLUSTERS (READ-ONLY) — N3b review")
        print("=" * 74)
        for slug in _LEAVES:
            cat = db.query(Category).filter_by(slug=slug).first()
            if cat is None:
                print(f"\n## {slug}: MISSING")
                continue
            rows = (
                db.query(Entity)
                .join(EntityCategory, EntityCategory.entity_id == Entity.id)
                .filter(
                    EntityCategory.category_id == cat.id,
                    EntityCategory.is_primary.is_(True),
                    Entity.is_active.is_(True),
                )
                .all()
            )
            clusters: dict[str, list[Entity]] = {}
            for e in rows:
                clusters.setdefault(_norm_addr(_addr_for(db, e.id)), []).append(e)

            multi = {a: es for a, es in clusters.items() if a and len(es) > 1}
            demote_candidates = 0
            print(f"\n## {slug}  (primary rows: {len(rows)}; shared-address clusters: {len(multi)})")
            for addr, es in sorted(multi.items(), key=lambda kv: -len(kv[1])):
                print(f"\n  @ {addr}  ({len(es)} rows)")
                kinds = [(_kind(e.name), e) for e in es]
                has_practice = any(k.startswith("PRACTICE") for k, _ in kinds)
                for k, e in sorted(kinds, key=lambda t: t[0]):
                    demote = has_practice and k.startswith("INDIVIDUAL")
                    if demote:
                        demote_candidates += 1
                    flag = "  <-- demote candidate" if demote else ""
                    print(f"    [{k:11s}] {e.name[:44]:44s} {e.id}{flag}")
            print(f"\n  => {demote_candidates} demote candidate(s) in {slug} "
                  f"(individuals sharing an address with a named practice)")
    print("\nREAD-ONLY — no writes. Review the demote candidates, then I'll build a "
          "gated demote script for the approved rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
