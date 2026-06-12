"""Set a place entity's official website contact point (DRY-RUN by default; gated).

Provider-less civic places (the Aquatic Center, a library) render a leaf "place
card" that links OUT to an official page when the entity has a ``website``
contact point (``app/categories/leaf_pages._place_website``). This upserts that
one contact-point row so the card becomes a link.

Match the entity by ``--slug`` (exact) or ``--name`` (case-insensitive exact).
Refuses to write if the match is ambiguous (more than one entity).

DEFAULT IS DRY-RUN. ``--apply`` requires ``--confirm``. Prints the sanitized DB
target every run (the repo .env can point DATABASE_URL at prod).

    .venv\\Scripts\\python.exe scripts\\set_place_website.py --name "Lake Havasu City Aquatic Center" --url https://www.lhcaz.gov/parks-recreation/aquatic-center
    ... --apply --confirm

PROD GATE (CLAUDE.md): dry-run, show Casey, approve, THEN a human applies.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import func  # noqa: E402

from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import ContactPoint, Entity  # noqa: E402

_WEB_KINDS = {"website", "web", "url"}


def _sanitized_target() -> str:
    url = DATABASE_URL or "(unset)"
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        url = f"{scheme}://{rest.split('@', 1)[1]}"
    return url


def run(*, url: str, slug: str | None = None, name: str | None = None,
        apply: bool = False, confirm: bool = False, session=None) -> int:
    own_session = session is None
    session = session or SessionLocal()
    try:
        print(f"DB target: {_sanitized_target()}\n")
        q = session.query(Entity)
        if slug:
            q = q.filter(Entity.slug == slug.strip())
        elif name:
            q = q.filter(func.lower(Entity.name) == name.strip().lower())
        else:
            print("ERROR: pass --slug or --name.")
            return 2
        ents = q.all()
        if not ents:
            print("No matching entity.")
            return 1
        if len(ents) > 1:
            print(f"AMBIGUOUS — {len(ents)} entities match; refusing to write:")
            for e in ents:
                print(f"  {e.id}  {e.name}  (slug={e.slug})")
            return 1
        ent = ents[0]
        existing = [
            cp for cp in (ent.contact_points or [])
            if (cp.kind or "").strip().lower() in _WEB_KINDS
        ]
        action = "update" if existing else "insert"
        print(f"entity: {ent.name} (slug={ent.slug})")
        print(f"website {action}: {url}")
        if existing:
            print(f"  (replacing {len(existing)} existing web contact point(s))")

        if not apply:
            print("\nDRY RUN — no rows written. Re-run with --apply --confirm to write.")
            return 0
        if not confirm:
            print(f"\nREFUSING TO WRITE — --apply requires --confirm. Target is {_sanitized_target()}.")
            return 0

        if existing:
            existing[0].value = url
            for extra in existing[1:]:
                session.delete(extra)
        else:
            session.add(
                ContactPoint(
                    entity_id=ent.id, kind="website", value=url,
                    created_at=datetime.now(UTC),
                )
            )
        session.commit()
        print(f"\nAPPLIED — website set on {ent.name}.")
        return 0
    finally:
        if own_session:
            session.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Set a place entity's website contact point.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--slug", help="Entity slug (exact).")
    g.add_argument("--name", help="Entity name (case-insensitive exact).")
    ap.add_argument("--url", required=True, help="Website URL to set.")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args(argv)
    return run(url=args.url, slug=args.slug, name=args.name, apply=args.apply, confirm=args.confirm)


if __name__ == "__main__":
    raise SystemExit(main())
