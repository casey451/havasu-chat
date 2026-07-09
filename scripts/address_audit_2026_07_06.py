"""T4.1 read-only audit — invalid street addresses (via the S2 validator).

Scans active providers, flags rows whose stored address fails
``app.contrib.address_clean.is_valid_street_address`` (plus-codes, PO boxes,
entity-suffix streets, leading placeholders, bare-city), and writes a review CSV
with the reason. READ-ONLY — no writes. The ingest guard (``clean_street_address``)
and any gated cleanup ride a follow-up once Casey confirms the bare-city handling.

    .venv\\Scripts\\python.exe scripts\\address_audit_2026_07_06.py
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.contrib.address_clean import is_valid_street_address, normalize_address  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

_REPORT_CSV = "docs/audits/2026-07/address_audit_2026-07-06.csv"

_PLUS = re.compile(r"\b[A-Z0-9]{4,}\+[A-Z0-9]{2,}\b")
_PO = re.compile(r"\bp\.?\s*o\.?\s*box\b", re.IGNORECASE)
_LEAD = re.compile(r"^\s*(the shops at|inside|online)", re.IGNORECASE)
_ENTITY = re.compile(r"\b(llc|inc|corp|co)\.?\s*$", re.IGNORECASE)
_BARE = re.compile(r"^\s*(lake havasu|havasu|arizona|az)\b", re.IGNORECASE)


def _reason(addr: str) -> str:
    street = addr.split(",", 1)[0].strip()
    if _PLUS.search(addr):
        return "plus_code"
    if _PO.search(addr):
        return "po_box"
    if _LEAD.search(addr):
        return "leading_placeholder"
    if _ENTITY.search(street):
        return "entity_suffix_street"
    if _BARE.match(street):
        return "bare_city_no_street"
    return "no_street_number"


def main() -> int:
    with SessionLocal() as db:
        provs = db.scalars(
            select(Provider).where(Provider.is_active.is_(True), Provider.address.isnot(None))
        ).all()
        rows_out: list[dict] = []
        for p in provs:
            if is_valid_street_address(p.address):
                continue
            rows_out.append({
                "provider_id": str(p.id), "provider_name": p.provider_name,
                "address": normalize_address(p.address) or "", "reason": _reason(p.address or ""),
                "source": p.source or "",
            })

    out = Path(_REPORT_CSV)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["provider_id", "provider_name", "address", "reason", "source"])
        w.writeheader()
        w.writerows(rows_out)

    by_reason: Counter[str] = Counter(r["reason"] for r in rows_out)
    print(f"active w/ address scanned: {len(provs)}  invalid: {len(rows_out)}")
    for reason, n in by_reason.most_common():
        print(f"  {reason:24} {n}")
    print(f"\nreport written: {out}")
    print("READ-ONLY audit — no writes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
