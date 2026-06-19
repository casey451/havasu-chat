"""Transaction-rollback DRY-RUN of the Slice 4 structural migration.

Executes the EXACT upgrade SQL from
``alembic/versions/iav2struct1_phase2_structural_taxonomy.py`` inside a single
transaction and then ROLLS BACK — nothing is ever committed. Prints the real row
counts each step would change, so we can confirm the migration runs clean on the
live Postgres DB and touches exactly the expected rows BEFORE it deploys.

Safe to run against prod: no commit happens (``rollback()`` in ``finally``).
Usage:  python scripts/dryrun_taxonomy_v2_migration.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

import sqlalchemy as sa  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402


def _dept_id(conn, slug):
    return conn.execute(
        sa.text("SELECT id FROM categories WHERE slug = :s AND level = 0"), {"s": slug}
    ).scalar()


def _leaf_id(conn, slug):
    return conn.execute(
        sa.text("SELECT id FROM categories WHERE slug = :s AND level = 1"), {"s": slug}
    ).scalar()


def _children(conn, dept_id):
    if dept_id is None:
        return None
    return conn.execute(
        sa.text("SELECT COUNT(*) FROM categories WHERE parent_id = :p AND level = 1"),
        {"p": dept_id},
    ).scalar()


def main():
    db = SessionLocal()
    conn = db.connection()
    try:
        print("=== Slice 4 migration DRY-RUN (executes in a transaction, then ROLLS BACK) ===\n")

        # 1. MERGE
        ttd = _dept_id(conn, "things-to-do-and-attractions")
        out = _dept_id(conn, "outdoors-and-recreation")
        print(f"[merge] before: things-to-do-and-attractions id={ttd} children={_children(conn, ttd)}; "
              f"outdoors-and-recreation id={out} children={_children(conn, out)}")
        if ttd is not None and out is not None:
            r = conn.execute(
                sa.text("UPDATE categories SET parent_id = :ttd WHERE parent_id = :out AND level = 1"),
                {"ttd": ttd, "out": out},
            )
            d = conn.execute(sa.text("DELETE FROM categories WHERE slug = 'outdoors-and-recreation' AND level = 0"))
            print(f"[merge] re-parented {r.rowcount} leaves; deleted {d.rowcount} outdoors dept; "
                  f"after: things-to-do-and-attractions children={_children(conn, ttd)}")

        # 2. SPLIT
        civic = _dept_id(conn, "community-and-civic")
        print(f"\n[split] before: community-and-civic id={civic} children={_children(conn, civic)}")
        if civic is not None:
            conn.execute(sa.text(
                "UPDATE categories SET slug='city-and-government', name='City & Government' "
                "WHERE slug='community-and-civic' AND level=0"))
            conn.execute(sa.text(
                "INSERT INTO categories (slug,name,sort_order,parent_id,level,created_at) "
                "VALUES ('worship-and-nonprofits','Worship & Nonprofits',15,NULL,0,CURRENT_TIMESTAMP)"))
            wor = _dept_id(conn, "worship-and-nonprofits")
            r = conn.execute(sa.text(
                "UPDATE categories SET parent_id=:wor "
                "WHERE slug IN ('places-of-worship','nonprofits-and-charities') AND level=1"),
                {"wor": wor})
            city = _dept_id(conn, "city-and-government")
            print(f"[split] city-and-government id={city} children={_children(conn, city)}; "
                  f"worship-and-nonprofits id={wor} children={_children(conn, wor)} "
                  f"(re-parented {r.rowcount} worship leaves)")

        # 3. PROMOTE
        tat_leaf = _leaf_id(conn, "tattoo-and-piercing")
        print(f"\n[promote] tattoo-and-piercing leaf id={tat_leaf}")
        if tat_leaf is not None:
            conn.execute(sa.text(
                "INSERT INTO categories (slug,name,sort_order,parent_id,level,created_at) "
                "VALUES ('tattoo','Tattoo & Piercing',16,NULL,0,CURRENT_TIMESTAMP)"))
            tat = _dept_id(conn, "tattoo")
            r = conn.execute(sa.text(
                "UPDATE categories SET parent_id=:tat WHERE slug='tattoo-and-piercing' AND level=1"),
                {"tat": tat})
            print(f"[promote] created tattoo dept id={tat}; re-parented {r.rowcount} tattoo leaf; "
                  f"tattoo children={_children(conn, tat)}")

        print("\n=== ROLLING BACK — no changes committed ===")
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
