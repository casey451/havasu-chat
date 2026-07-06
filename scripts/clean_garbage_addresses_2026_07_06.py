"""T4.1 apply — blank GARBAGE addresses (plus-code / PO box / placeholder / …Llc).

Uses the S2 guard ``is_garbage_address``: sets ``address = NULL`` on active
providers whose stored address is a plus-code, PO box, leading placeholder, or
entity-suffix street. Honest-but-partial addresses (bare city, street with no
house number) are LEFT untouched — only misleading junk is dropped. The matching
ingest guard (``strip_garbage_address`` in normalize_payload) stops new ones.

DRY-RUN by default; ``--apply`` writes and emits an undo CSV.

    .venv\\Scripts\\python.exe scripts\\clean_garbage_addresses_2026_07_06.py            # dry-run
    .venv\\Scripts\\python.exe scripts\\clean_garbage_addresses_2026_07_06.py --apply    # write (gated)
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from sqlalchemy import select  # noqa: E402

from app.contrib.address_clean import is_garbage_address  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

_UNDO_CSV = "clean_garbage_addresses_undo_2026-07-06.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Blank garbage provider addresses.")
    parser.add_argument("--apply", action="store_true", help="write changes (else dry-run)")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        provs = db.scalars(
            select(Provider).where(Provider.is_active.is_(True), Provider.address.isnot(None))
        ).all()
        targets = [p for p in provs if is_garbage_address(p.address)]

        print(f"active w/ address={len(provs)}  garbage addresses to blank={len(targets)}")
        for p in targets:
            print(f"    {p.provider_name[:34]!r:36} addr={p.address!r}")

        if not targets:
            print("Nothing to clean.")
            return 0
        if not args.apply:
            print("\nDRY RUN — no DB writes. Re-run with --apply to write (prod-data gate).")
            return 0

        with open(_UNDO_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "provider_name", "old_address"])
            for p in targets:
                w.writerow([p.id, p.provider_name, p.address])

        for p in targets:
            p.address = None
        db.commit()
        print(f"APPLIED: blanked {len(targets)} garbage addresses. Undo CSV: {_UNDO_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
