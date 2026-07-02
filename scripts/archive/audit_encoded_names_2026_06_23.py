"""Read-only audit: do any stored names contain literal HTML entities?

Phase 3.5 (FIX_SPEC_2026-06-23). The live audit saw "Christine&#39;s" /
"Sweet Treats &amp; More" on /categories. That is the NORMAL output of Jinja
auto-escaping a CLEAN name ("Christine's" → ``&#39;`` in the HTML source; the
browser displays the apostrophe). A real data bug would be a name DOUBLE-stored
as the literal text ``&#39;`` / ``&amp;`` in the database — then the page would
show the raw entity in the browser too.

This script is READ-ONLY (no writes, dry-run by definition). It counts and
samples Provider / Entity / Place names that contain a literal HTML entity.

  • 0 rows  → names are clean; 3.5 was the stale render. No action.
  • >0 rows → a real data bug: the fix is unescape-at-ingest (already done for
    the event paths) + a one-time backfill of these rows. That backfill is a
    PROD DATA WRITE and must follow CLAUDE.md: dry-run → show counts → Casey
    approves → apply. This script is the dry-run/count step; it never writes.

Run (against whatever DATABASE_URL points to — prod by default in this repo):

    .venv\\Scripts\\python.exe scripts\\audit_encoded_names_2026_06_23.py
"""

from __future__ import annotations

from sqlalchemy import func, or_

from app.db.database import SessionLocal
from app.db.models import Entity, Event, Provider

# Literal HTML-entity signatures of escaped/double-escaped storage. A bare "&"
# is NOT included — "Sweet Treats & More" stored correctly contains a literal &
# and is not a bug.
_ENTITY_PATTERNS = ["%&amp;%", "%&#3%", "%&#39;%", "%&quot;%", "%&apos;%", "%&lt;%", "%&gt;%"]


def _audit(db, model, col, label: str) -> int:
    cond = or_(*[col.like(p) for p in _ENTITY_PATTERNS])
    n = db.query(func.count()).select_from(model).filter(cond).scalar() or 0
    print(f"{label}: {n} row(s) with a literal HTML entity")
    if n:
        for (val,) in db.query(col).filter(cond).limit(15):
            print(f"    {val!r}")
    return n


def main() -> None:
    total = 0
    with SessionLocal() as db:
        total += _audit(db, Provider, Provider.provider_name, "Provider.provider_name")
        total += _audit(db, Entity, Entity.name, "Entity.name")
        total += _audit(db, Event, Event.title, "Event.title")
    print("-" * 60)
    if total == 0:
        print("CLEAN: no entity-encoded names. Phase 3.5 = stale render; no data op.")
    else:
        print(f"FOUND {total} encoded name(s). This is a gated prod backfill —")
        print("unescape these rows via the dry-run -> counts -> approve -> apply path.")


if __name__ == "__main__":
    main()
