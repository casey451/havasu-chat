"""Phase 2 (IA v2) structural taxonomy changes: merge, split, promote.

Revision ID: iav2struct1
Revises: c9billingscaf
Create Date: 2026-06-16

Data-only restructure of the level-0 department tree (matched by slug, reversible):

  1. MERGE   outdoors-and-recreation INTO things-to-do-and-attractions
             (re-parent outdoors leaves; delete the now-childless outdoors row).
             The surviving department keeps slug 'things-to-do-and-attractions'
             (a 'things-to-do' master-bucket row already owns that slug); its
             USER-FACING label becomes "Things to Do" via display_labels.py.
  2. SPLIT   community-and-civic -> city-and-government (renamed in place, keeps
             its city leaves) + worship-and-nonprofits (new dept; re-parent
             places-of-worship + nonprofits-and-charities to it).
  3. PROMOTE tattoo-and-piercing leaf -> its own 'tattoo' department
             ('tattoo' avoids a slug collision with the leaf slug).

Every operation is guarded on the source rows EXISTING, so on a migrations-only
database (e.g. the pytest temp DB, where the 15-dept tree is seeded by
scripts/seed_taxonomy.py, NOT migrations) this migration is a clean no-op. Its
real effect is on the seeded prod database; confirm with
scripts/inspect_taxonomy_v2_changes.py before deploy. No schema change.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "iav2struct1"
down_revision: Union[str, Sequence[str], None] = "c9billingscaf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OUTDOORS_LEAVES = (
    "parks-and-playgrounds",
    "golf-courses",
    "hiking-trails",
    "disc-golf",
    "off-road-and-ohv",
    "dog-parks",
)
_WORSHIP_LEAVES = ("places-of-worship", "nonprofits-and-charities")


def _dept_id(conn, slug):
    return conn.execute(
        sa.text("SELECT id FROM categories WHERE slug = :s AND level = 0"), {"s": slug}
    ).scalar()


def _leaf_id(conn, slug):
    return conn.execute(
        sa.text("SELECT id FROM categories WHERE slug = :s AND level = 1"), {"s": slug}
    ).scalar()


def upgrade() -> None:
    conn = op.get_bind()

    # 1. MERGE outdoors -> things-to-do-and-attractions (slug unchanged).
    ttd = _dept_id(conn, "things-to-do-and-attractions")
    out = _dept_id(conn, "outdoors-and-recreation")
    if ttd is not None and out is not None:
        conn.execute(
            sa.text("UPDATE categories SET parent_id = :ttd WHERE parent_id = :out AND level = 1"),
            {"ttd": ttd, "out": out},
        )
        conn.execute(sa.text("DELETE FROM categories WHERE slug = 'outdoors-and-recreation' AND level = 0"))

    # 2. SPLIT community-and-civic -> city-and-government + worship-and-nonprofits.
    if _dept_id(conn, "community-and-civic") is not None:
        conn.execute(
            sa.text(
                "UPDATE categories SET slug = 'city-and-government', name = 'City & Government' "
                "WHERE slug = 'community-and-civic' AND level = 0"
            )
        )
        if _dept_id(conn, "worship-and-nonprofits") is None:
            conn.execute(
                sa.text(
                    "INSERT INTO categories (slug, name, sort_order, parent_id, level, created_at) "
                    "VALUES ('worship-and-nonprofits', 'Worship & Nonprofits', 15, NULL, 0, CURRENT_TIMESTAMP)"
                )
            )
        wor = _dept_id(conn, "worship-and-nonprofits")
        if wor is not None:
            conn.execute(
                sa.text(
                    "UPDATE categories SET parent_id = :wor WHERE slug IN :leaves AND level = 1"
                ).bindparams(sa.bindparam("leaves", expanding=True)),
                {"wor": wor, "leaves": list(_WORSHIP_LEAVES)},
            )

    # 3. PROMOTE tattoo-and-piercing leaf -> 'tattoo' department.
    if _leaf_id(conn, "tattoo-and-piercing") is not None:
        if _dept_id(conn, "tattoo") is None:
            conn.execute(
                sa.text(
                    "INSERT INTO categories (slug, name, sort_order, parent_id, level, created_at) "
                    "VALUES ('tattoo', 'Tattoo & Piercing', 16, NULL, 0, CURRENT_TIMESTAMP)"
                )
            )
        tat = _dept_id(conn, "tattoo")
        if tat is not None:
            conn.execute(
                sa.text("UPDATE categories SET parent_id = :tat WHERE slug = 'tattoo-and-piercing' AND level = 1"),
                {"tat": tat},
            )


def downgrade() -> None:
    conn = op.get_bind()

    # Reverse 3.
    if _dept_id(conn, "tattoo") is not None:
        beauty = _dept_id(conn, "beauty-and-personal-care")
        if beauty is not None:
            conn.execute(
                sa.text("UPDATE categories SET parent_id = :b WHERE slug = 'tattoo-and-piercing' AND level = 1"),
                {"b": beauty},
            )
        conn.execute(sa.text("DELETE FROM categories WHERE slug = 'tattoo' AND level = 0"))

    # Reverse 2.
    if _dept_id(conn, "city-and-government") is not None:
        conn.execute(
            sa.text(
                "UPDATE categories SET slug = 'community-and-civic', name = 'Community & Civic' "
                "WHERE slug = 'city-and-government' AND level = 0"
            )
        )
        civic = _dept_id(conn, "community-and-civic")
        if civic is not None:
            conn.execute(
                sa.text(
                    "UPDATE categories SET parent_id = :c WHERE slug IN :leaves AND level = 1"
                ).bindparams(sa.bindparam("leaves", expanding=True)),
                {"c": civic, "leaves": list(_WORSHIP_LEAVES)},
            )
        conn.execute(sa.text("DELETE FROM categories WHERE slug = 'worship-and-nonprofits' AND level = 0"))

    # Reverse 1.
    ttd = _dept_id(conn, "things-to-do-and-attractions")
    if ttd is not None and _dept_id(conn, "outdoors-and-recreation") is None:
        conn.execute(
            sa.text(
                "INSERT INTO categories (slug, name, sort_order, parent_id, level, created_at) "
                "VALUES ('outdoors-and-recreation', 'Outdoors & Recreation', 2, NULL, 0, CURRENT_TIMESTAMP)"
            )
        )
        out = _dept_id(conn, "outdoors-and-recreation")
        if out is not None:
            conn.execute(
                sa.text(
                    "UPDATE categories SET parent_id = :out WHERE slug IN :leaves AND level = 1"
                ).bindparams(sa.bindparam("leaves", expanding=True)),
                {"out": out, "leaves": list(_OUTDOORS_LEAVES)},
            )
