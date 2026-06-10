"""One-shot eat-bucket cleanup: audit -> show flagged rows -> confirm -> apply.

Wraps audit_eat_bucket_pollution + fix_eat_bucket_pollution into a single run
while keeping the human gate: nothing is written until you type "yes" at the
prompt, after seeing exactly which rows would change and which database the
script is connected to.

Usage:
    .venv\\Scripts\\python.exe scripts\\eat_bucket_cleanup.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlsplit

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.database import DATABASE_URL  # noqa: E402
from scripts.archive.fix_eat_bucket_pollution import run  # noqa: E402


def _db_label(url: str) -> str:
    """Human-readable DB target with credentials stripped."""
    try:
        parts = urlsplit(url)
        if parts.scheme.startswith("sqlite"):
            return f"LOCAL SQLITE ({parts.path})"
        host = parts.hostname or "?"
        return f"{parts.scheme} @ {host}/{(parts.path or '').lstrip('/')}"
    except Exception:
        return "unknown"


def main() -> None:
    label = _db_label(DATABASE_URL)
    print(f"Database: {label}")
    if "sqlite" in label.lower():
        print(
            "\nWARNING: this is your LOCAL dev database, not prod."
            "\nRun pull_prod_env.ps1 (or set DATABASE_URL) first if you meant prod."
        )
        if input("Continue against the local DB anyway? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return

    print("\n--- Dry run (no writes) ---")
    flagged = run(apply=False)
    if flagged == 0:
        print("\nNothing to fix. Done.")
        return

    answer = input(f"\nClear subcategory on these {flagged} row(s)? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        print("Aborted — nothing written.")
        return

    print("\n--- Applying ---")
    run(apply=True)
    print("\nDone. Re-running audit to confirm clean:")
    run(apply=False)


if __name__ == "__main__":
    main()
