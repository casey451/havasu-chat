"""Phase 3.2 — category taxonomy rewrite, audited backfill, district seed, close-out.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-05-12

Data pass: rename 7 category slugs; delete ``family`` + ``community`` (guarded);
insert ``classes-sports-recreation`` + ``public-civic-resources``; reset ``sort_order``
per ``outputs/chatgpt_taxonomy_research_synthesis.md`` §1 table order (Tier 1 → 2 → 3).

Provider/program category backfill follows ``docs/maintainability/category_backfill_mapping_audit_2026-05-14.md`` §2
(portable subquery UPDATEs; ``AND category_id IS NULL`` idempotency). **Bucket C (Pass 4)** encodes three
explicit NULL UPDATEs only (``beauty_personal_care``, ``tourism``, ``barbershop``). Operator locks A.4
(K-12 / charter / public schools under ``education``) and A.5 (bowling / arcades / mini golf as subsets of
``entertainment_attractions``) are **documented inline at Pass 2** — no separate Pass-4 SQL.

District seed: 10 deterministic UUID rows, ``paragraph=NULL`` (operator path (b) lock).
``entities.district_id`` is backfilled from ``locations.district`` string (this codebase
never had ``entities.district`` — see §13 deviation). ``entities.featured`` from
``providers.featured``. ``users.preferred_mode`` is a documented no-op (Phase 3.1 shipped
NOT NULL + server default).

Downgrade restores pre-3.2 category rows/slugs using ``_phase32_category_bak`` (family/community
original integer ids).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Deterministic district PKs (author-time; idempotent seed + downgrade targeting).
_DISTRICT_ROWS: tuple[tuple[str, str, str, int], ...] = (
    ("d7c1cfb2-1d9d-4aaa-9564-53bf67726e46", "english-village", "English Village", 1),
    ("c9c282e4-bc01-4988-af11-aea4aeb4e14c", "downtown-main-street", "Downtown / Main Street", 2),
    ("b32eec3a-cc24-49d6-8037-ce36b020c8b9", "north-end", "North End", 3),
    ("c445b60f-4056-4a6b-bec5-65a6845ce043", "lakefront", "Lakefront", 4),
    ("156e5362-b028-4e10-885d-1d190e853dae", "mesquite-bay", "Mesquite Bay", 5),
    ("8ecb1abd-56bf-4861-8603-098e7c6f6880", "highway-95-corridor", "Highway 95 Corridor", 6),
    ("2a221404-e2b9-4877-91ab-63f30b74aa35", "site-six", "Site Six", 7),
    ("df8e9766-b310-493f-9470-796ff3e06bb1", "pittsburgh-point", "Pittsburgh Point", 8),
    ("d88f81a7-2340-4a68-aed4-826fc8c43a4a", "castle-rock-area", "Castle Rock area", 9),
    ("4410ad92-4ae0-43ac-bb86-35040bb66975", "south-side", "South side", 10),
)

_SORT_ORDER_SYNTHESIS: tuple[tuple[str, int], ...] = (
    # outputs/chatgpt_taxonomy_research_synthesis.md §1 — table order within each tier.
    ("home-property-services", 1),
    ("health-wellness-care", 2),
    ("eat-drink", 3),
    ("on-the-water", 4),
    ("auto-rv-fuel", 5),
    ("shopping-essentials", 6),
    ("outdoors-parks-trails", 7),
    ("lodging-vacation-rentals", 8),
    ("pets", 9),
    ("events", 10),
    ("classes-sports-recreation", 11),
    ("public-civic-resources", 12),
)


def upgrade() -> None:
    bind = op.get_bind()

    op.execute(sa.text("DROP TABLE IF EXISTS _phase32_category_bak"))
    op.create_table(
        "_phase32_category_bak",
        sa.Column("slug", sa.String(length=64), primary_key=True),
        sa.Column("old_id", sa.Integer(), nullable=False),
    )
    for slug in ("family", "community"):
        row = bind.execute(
            sa.text("SELECT id FROM categories WHERE slug = :s"), {"s": slug}
        ).first()
        if row is not None:
            bind.execute(
                sa.text(
                    "INSERT INTO _phase32_category_bak (slug, old_id) VALUES (:slug, :oid)"
                ),
                {"slug": slug, "oid": int(row[0])},
            )

    with op.batch_alter_table("districts", schema=None) as batch_op:
        batch_op.alter_column(
            "paragraph",
            existing_type=sa.Text(),
            nullable=True,
        )

    # §5.1 step 1 — rename 7 surviving slugs (display names per synthesis where set).
    op.execute(
        sa.text(
            "UPDATE categories SET slug = 'eat-drink', name = 'Eat & Drink' "
            "WHERE slug = 'eat-and-drink'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE categories SET slug = 'home-property-services', "
            "name = 'Home & Property Services' WHERE slug = 'home-services'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE categories SET slug = 'health-wellness-care', "
            "name = 'Health, Wellness & Care' WHERE slug = 'health'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE categories SET slug = 'outdoors-parks-trails', "
            "name = 'Outdoors, Parks & Trails' WHERE slug = 'outdoors-and-parks'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE categories SET slug = 'shopping-essentials', "
            "name = 'Shopping, Grocery & Essentials' WHERE slug = 'shopping'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE categories SET slug = 'auto-rv-fuel', name = 'Auto, RV & Fuel' "
            "WHERE slug = 'auto-and-gas'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE categories SET slug = 'lodging-vacation-rentals', "
            "name = 'Lodging & Vacation Rentals' WHERE slug = 'lodging'"
        )
    )

    # Clear FKs to rows we are about to delete (providers / programs / entity_categories).
    op.execute(
        sa.text(
            "UPDATE providers SET category_id = NULL WHERE category_id IN "
            "(SELECT id FROM categories WHERE slug IN ('family', 'community'))"
        )
    )
    op.execute(
        sa.text(
            "UPDATE programs SET category_id = NULL WHERE category_id IN "
            "(SELECT id FROM categories WHERE slug IN ('family', 'community'))"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM entity_categories WHERE category_id IN "
            "(SELECT id FROM categories WHERE slug IN ('family', 'community'))"
        )
    )

    op.execute(sa.text("DELETE FROM categories WHERE slug IN ('family', 'community')"))

    now = datetime.now(UTC)
    cats_ins = sa.table(
        "categories",
        sa.column("slug", sa.String(64)),
        sa.column("name", sa.String(128)),
        sa.column("sort_order", sa.Integer()),
        sa.column("created_at", sa.DateTime()),
    )
    op.bulk_insert(
        cats_ins,
        [
            {
                "slug": "classes-sports-recreation",
                "name": "Classes, Sports & Recreation",
                "sort_order": 0,
                "created_at": now,
            },
            {
                "slug": "public-civic-resources",
                "name": "Public & Civic Resources",
                "sort_order": 0,
                "created_at": now,
            },
        ],
    )

    for slug, so in _SORT_ORDER_SYNTHESIS:
        bind.execute(
            sa.text("UPDATE categories SET sort_order = :so WHERE slug = :slug"),
            {"so": so, "slug": slug},
        )

    # --- Pass 1 — Bucket A + Bucket E (recreation) — providers ---
    _pa = [
        ("health_medical", "health-wellness-care"),
        ("food_drink", "eat-drink"),
        ("food", "eat-drink"),
        ("restaurant", "eat-drink"),
        ("bakery", "eat-drink"),
        ("home_services", "home-property-services"),
        ("general_contractor", "home-property-services"),
        ("plumbing", "home-property-services"),
        ("services", "home-property-services"),
        ("retail", "shopping-essentials"),
        ("lake_recreation", "on-the-water"),
        ("boat_repair", "on-the-water"),
        ("boat_rental", "on-the-water"),
        ("auto", "auto-rv-fuel"),
        ("lodging", "lodging-vacation-rentals"),
        ("pet", "pets"),
        ("pets", "pets"),
        ("veterinary", "pets"),
        ("event_venue", "events"),
        ("music", "events"),
        ("recreation", "classes-sports-recreation"),
    ]
    for legacy, slug in _pa:
        bind.execute(
            sa.text(
                "UPDATE providers SET category_id = "
                "(SELECT id FROM categories WHERE slug = :slug) "
                "WHERE category = :leg AND category_id IS NULL"
            ),
            {"slug": slug, "leg": legacy},
        )
        bind.execute(
            sa.text(
                "UPDATE programs SET category_id = "
                "(SELECT id FROM categories WHERE slug = :slug) "
                "WHERE activity_category = :leg AND category_id IS NULL"
            ),
            {"slug": slug, "leg": legacy},
        )

    # --- Pass 2 — Bucket B (improved homes) ---
    # Operator lock A.4 (documented only — no separate SQL): audit memo §2 line 64 treats
    # K-12 / charter / public school as a sub-question of ``education`` (not standalone
    # Provider.category strings). Session-20 lock confirms Pass 2's ``education`` →
    # ``classes-sports-recreation`` covers public schools (vs ``public-civic-resources``).
    for leg in ("childcare_education", "education", "edu"):
        bind.execute(
            sa.text(
                "UPDATE providers SET category_id = "
                "(SELECT id FROM categories WHERE slug = 'classes-sports-recreation') "
                "WHERE category = :leg AND category_id IS NULL"
            ),
            {"leg": leg},
        )
        bind.execute(
            sa.text(
                "UPDATE programs SET category_id = "
                "(SELECT id FROM categories WHERE slug = 'classes-sports-recreation') "
                "WHERE activity_category = :leg AND category_id IS NULL"
            ),
            {"leg": leg},
        )
    bind.execute(
        sa.text(
            "UPDATE providers SET category_id = "
            "(SELECT id FROM categories WHERE slug = 'public-civic-resources') "
            "WHERE category = 'religion_community' AND category_id IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE programs SET category_id = "
            "(SELECT id FROM categories WHERE slug = 'public-civic-resources') "
            "WHERE activity_category = 'religion_community' AND category_id IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE providers SET category_id = "
            "(SELECT id FROM categories WHERE slug = 'health-wellness-care') "
            "WHERE category = 'fitness_sports' AND category_id IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE programs SET category_id = "
            "(SELECT id FROM categories WHERE slug = 'health-wellness-care') "
            "WHERE activity_category = 'fitness_sports' AND category_id IS NULL"
        )
    )

    # Operator lock A.5 (documented only — no Phase 3.2 SQL): audit memo §2 line 84 — bowling,
    # arcades, mini golf are subsets of ``entertainment_attractions``. Brief §5.2 + audit defer
    # that cohort to Phase 5 (NULL ``category_id`` + ``google_primary_category`` split). Session-20
    # triage lock records: when the split lands, bowling / arcades / mini golf →
    # ``classes-sports-recreation`` (implemented in Phase 5, not here). Intentionally no UPDATE
    # for ``entertainment_attractions`` in this migration.

    # --- Pass 3 — professional services NULL queue ---
    bind.execute(
        sa.text(
            "UPDATE providers SET category_id = NULL WHERE category IN "
            "('insurance', 'financial', 'legal', 'real_estate', 'professional_services') "
            "AND category_id IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE programs SET category_id = NULL WHERE activity_category IN "
            "('insurance', 'financial', 'legal', 'real_estate', 'professional_services') "
            "AND category_id IS NULL"
        )
    )

    # --- Pass 4 — Bucket C: three explicit NULL UPDATEs (A.1–A.3 only) ---
    # A.4 (schools) and A.5 (bowling/arcades/mini golf) are documented-only locks at Pass 2
    # (see comments above); they are not separate UPDATE targets in Pass 4.
    for leg in ("beauty_personal_care", "tourism", "barbershop"):
        bind.execute(
            sa.text(
                "UPDATE providers SET category_id = NULL WHERE category = :leg "
                "AND category_id IS NULL"
            ),
            {"leg": leg},
        )
        bind.execute(
            sa.text(
                "UPDATE programs SET category_id = NULL WHERE activity_category = :leg "
                "AND category_id IS NULL"
            ),
            {"leg": leg},
        )

    # --- §5.3 district seed (idempotent) ---
    n_d = bind.execute(sa.text("SELECT COUNT(*) FROM districts")).scalar_one()
    if int(n_d) == 0:
        dist_tbl = sa.table(
            "districts",
            sa.column("id", sa.String(36)),
            sa.column("slug", sa.String(64)),
            sa.column("name", sa.String(128)),
            sa.column("paragraph", sa.Text()),
            sa.column("display_order", sa.Integer()),
            sa.column("created_at", sa.DateTime()),
            sa.column("updated_at", sa.DateTime()),
        )
        ts = datetime.now(UTC)
        op.bulk_insert(
            dist_tbl,
            [
                {
                    "id": rid,
                    "slug": slug,
                    "name": name,
                    "paragraph": None,
                    "display_order": disp,
                    "created_at": ts,
                    "updated_at": ts,
                }
                for rid, slug, name, disp in _DISTRICT_ROWS
            ],
        )

    # --- §5.4 district_id from locations.district (no entities.district column in schema) ---
    bind.execute(
        sa.text(
            "UPDATE entities SET district_id = ("
            " SELECT d.id FROM districts AS d"
            " INNER JOIN locations AS l ON l.entity_id = entities.id"
            " WHERE LOWER(TRIM(d.name)) = LOWER(TRIM(l.district))"
            " LIMIT 1"
            ") WHERE district_id IS NULL AND EXISTS ("
            " SELECT 1 FROM locations AS l2 WHERE l2.entity_id = entities.id"
            " AND l2.district IS NOT NULL AND TRIM(l2.district) != ''"
            ")"
        )
    )

    # --- §5.5 featured backfill ---
    bind.execute(
        sa.text(
            "UPDATE entities SET featured = ("
            " SELECT providers.featured FROM providers"
            " WHERE providers.entity_id = entities.id"
            ") WHERE entity_type = 'commercial' AND id IN ("
            " SELECT entity_id FROM providers WHERE featured IS TRUE"
            ") AND EXISTS (SELECT 1 FROM providers WHERE providers.entity_id = entities.id)"
        )
    )

    # §5.6 users.preferred_mode — Phase 3.1 already NOT NULL + default; no SQL.


def downgrade() -> None:
    bind = op.get_bind()

    bind.execute(
        sa.text(
            "UPDATE entities SET featured = 0 WHERE id IN ("
            " SELECT entity_id FROM providers WHERE featured IS TRUE"
            ")"
        )
    )
    bind.execute(sa.text("UPDATE entities SET district_id = NULL"))

    ids_in = ", ".join(f"'{r[0]}'" for r in _DISTRICT_ROWS)
    bind.execute(sa.text(f"DELETE FROM districts WHERE id IN ({ids_in})"))

    _mapped_legacy = (
        "health_medical",
        "food_drink",
        "food",
        "restaurant",
        "bakery",
        "home_services",
        "general_contractor",
        "plumbing",
        "services",
        "retail",
        "lake_recreation",
        "boat_repair",
        "boat_rental",
        "auto",
        "lodging",
        "pet",
        "pets",
        "veterinary",
        "event_venue",
        "music",
        "recreation",
        "childcare_education",
        "education",
        "edu",
        "religion_community",
        "fitness_sports",
    )
    in_sql = ", ".join(f"'{s}'" for s in _mapped_legacy)
    bind.execute(sa.text(f"UPDATE providers SET category_id = NULL WHERE category IN ({in_sql})"))
    bind.execute(
        sa.text(f"UPDATE programs SET category_id = NULL WHERE activity_category IN ({in_sql})")
    )

    op.execute(sa.text("DELETE FROM categories WHERE slug IN ('classes-sports-recreation', 'public-civic-resources')"))

    bak_rows = bind.execute(sa.text("SELECT slug, old_id FROM _phase32_category_bak")).all()
    bak = {str(r[0]): int(r[1]) for r in bak_rows}
    fam_id = bak.get("family")
    com_id = bak.get("community")
    now = datetime.now(UTC)
    if fam_id is not None:
        bind.execute(
            sa.text(
                "INSERT INTO categories (id, slug, name, sort_order, created_at) "
                "VALUES (:id, 'family', 'Family', 30, :ts)"
            ),
            {"id": fam_id, "ts": now},
        )
    if com_id is not None:
        bind.execute(
            sa.text(
                "INSERT INTO categories (id, slug, name, sort_order, created_at) "
                "VALUES (:id, 'community', 'Community', 120, :ts)"
            ),
            {"id": com_id, "ts": now},
        )

    op.execute(
        sa.text(
            "UPDATE categories SET slug = 'lodging', name = 'Lodging' "
            "WHERE slug = 'lodging-vacation-rentals'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE categories SET slug = 'auto-and-gas', name = 'Auto & Gas' "
            "WHERE slug = 'auto-rv-fuel'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE categories SET slug = 'shopping', name = 'Shopping' "
            "WHERE slug = 'shopping-essentials'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE categories SET slug = 'outdoors-and-parks', name = 'Outdoors & Parks' "
            "WHERE slug = 'outdoors-parks-trails'"
        )
    )
    op.execute(
        sa.text("UPDATE categories SET slug = 'health', name = 'Health' WHERE slug = 'health-wellness-care'")
    )
    op.execute(
        sa.text(
            "UPDATE categories SET slug = 'home-services', name = 'Home Services' "
            "WHERE slug = 'home-property-services'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE categories SET slug = 'eat-and-drink', name = 'Eat & Drink' "
            "WHERE slug = 'eat-drink'"
        )
    )

    # Pre-3.2 sort_order from e7f8a9b0c1d2 seed (reference for downgrade / inheritance).
    _legacy_sort = (
        ("eat-and-drink", 10),
        ("events", 20),
        ("family", 30),
        ("home-services", 40),
        ("health", 50),
        ("on-the-water", 60),
        ("outdoors-and-parks", 70),
        ("shopping", 80),
        ("auto-and-gas", 90),
        ("lodging", 100),
        ("pets", 110),
        ("community", 120),
    )
    for slug, so in _legacy_sort:
        bind.execute(
            sa.text("UPDATE categories SET sort_order = :so WHERE slug = :slug"),
            {"so": so, "slug": slug},
        )

    op.drop_table("_phase32_category_bak")

    with op.batch_alter_table("districts", schema=None) as batch_op:
        batch_op.alter_column(
            "paragraph",
            existing_type=sa.Text(),
            nullable=False,
        )
