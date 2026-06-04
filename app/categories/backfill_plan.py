"""Single source of truth for the Provider.category_id backfill.

Both the alembic data migration (which applies it to prod on deploy) and the
read-only dry-run script import these, so the proposed counts always match what
actually gets written.

Decisions (the blueprint asks these legacy->bucket calls to be hand-made):
  * things-to-do        -> things-to-do          (new top-level bucket)
  * professional_services -> professional         (new bucket; not home-services)
  * religion_community  -> public-civic-resources (community/civic)
  * beauty_personal_care -> beauty-care           (new bucket)
  * recreation          -> classes-sports-recreation
  * services            -> home-property-services
  * uncategorized / misc -> LEFT NULL (genuinely unclassified — honest, not guessed)

Only rows with category_id IS NULL are touched; existing assignments are never
overwritten.
"""

from __future__ import annotations

# Tier-1 Category buckets that the routes (CATEGORY_FILTERS) expose but the
# Category table doesn't have rows for yet. Seeded so every route has a bucket.
# (slug, display name, sort_order)
NEW_BUCKETS: tuple[tuple[str, str, int], ...] = (
    ("things-to-do", "Things to Do", 30),
    ("professional-services", "Professional Services", 40),
    ("beauty-care", "Beauty & Personal Care", 41),
    ("attractions", "Attractions", 31),
    ("services", "Services", 42),
)

# legacy Provider.category value -> target Category slug. Conservative, hand-made.
LEGACY_TO_BUCKET: dict[str, str] = {
    "things-to-do": "things-to-do",
    "professional_services": "professional-services",
    "religion_community": "public-civic-resources",
    "beauty_personal_care": "beauty-care",
    "recreation": "classes-sports-recreation",
    "services": "home-property-services",
}


# Executable form shared by the alembic migration and its test, so the logic is
# exercised once. Operates on a raw Connection (no ORM) and is idempotent.
def _tables():
    import sqlalchemy as sa

    categories = sa.table(
        "categories",
        sa.column("id", sa.Integer),
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("sort_order", sa.Integer),
    )
    providers = sa.table(
        "providers",
        sa.column("category", sa.String),
        sa.column("category_id", sa.Integer),
    )
    return categories, providers


def seed_and_backfill(conn) -> dict[str, int]:
    """Seed missing buckets, then assign category_id to NULL rows per the plan.

    Idempotent; only NULL rows are touched. Returns per-bucket assigned counts.
    """
    import sqlalchemy as sa

    categories, providers = _tables()
    existing = {r[0] for r in conn.execute(sa.select(categories.c.slug))}
    to_add = [
        {"slug": s, "name": n, "sort_order": o}
        for s, n, o in NEW_BUCKETS
        if s not in existing
    ]
    if to_add:
        conn.execute(sa.insert(categories), to_add)

    slug_to_id = {r[0]: r[1] for r in conn.execute(sa.select(categories.c.slug, categories.c.id))}
    counts: dict[str, int] = {}
    for legacy, bucket_slug in LEGACY_TO_BUCKET.items():
        cat_id = slug_to_id.get(bucket_slug)
        if cat_id is None:
            continue
        res = conn.execute(
            sa.update(providers)
            .where(providers.c.category == legacy)
            .where(providers.c.category_id.is_(None))
            .values(category_id=cat_id)
        )
        counts[legacy] = res.rowcount or 0
    return counts


def reverse_backfill(conn) -> None:
    """Undo: null out rows this plan set, then drop the seeded buckets."""
    import sqlalchemy as sa

    categories, providers = _tables()
    slug_to_id = {r[0]: r[1] for r in conn.execute(sa.select(categories.c.slug, categories.c.id))}
    for legacy, bucket_slug in LEGACY_TO_BUCKET.items():
        cat_id = slug_to_id.get(bucket_slug)
        if cat_id is None:
            continue
        conn.execute(
            sa.update(providers)
            .where(providers.c.category == legacy)
            .where(providers.c.category_id == cat_id)
            .values(category_id=None)
        )
    seeded = [s for s, _n, _o in NEW_BUCKETS]
    if seeded:
        conn.execute(sa.delete(categories).where(categories.c.slug.in_(seeded)))


# ---------------------------------------------------------------------------
# WP-9 step 2 -- the 13th canonical category, ``professional-services``
# ---------------------------------------------------------------------------
#
# The route/code taxonomy gained ``professional-services`` (split out of
# public-civic); prod's ``categories`` table only had the older ``professional``
# bucket. ``seed_professional_services`` adds the canonical row (no-op when the
# pivoted ``NEW_BUCKETS`` above already seeded it on a fresh DB) and repoints
# ``Provider.category_id`` for providers whose canonical
# ``primary_category='professional-services'`` -- but ONLY rows that are NULL or
# still point at the legacy ``professional`` bucket. A deliberate different
# assignment is never overwritten. Idempotent.

PROFESSIONAL_SERVICES_SLUG = "professional-services"
PROFESSIONAL_SERVICES_NAME = "Professional Services"
PROFESSIONAL_SERVICES_SORT = 40
_LEGACY_PROFESSIONAL_SLUG = "professional"


def _tables_ps():
    import sqlalchemy as sa

    categories, providers = _tables()
    providers_ps = sa.table(
        "providers",
        sa.column("category_id", sa.Integer),
        sa.column("primary_category", sa.String),
    )
    return categories, providers_ps


def seed_professional_services(conn) -> dict[str, int]:
    """Seed the canonical row + repoint category_id. Returns counts."""
    import sqlalchemy as sa

    categories, providers = _tables_ps()
    slug_to_id = {
        r[0]: r[1] for r in conn.execute(sa.select(categories.c.slug, categories.c.id))
    }
    new_id = slug_to_id.get(PROFESSIONAL_SERVICES_SLUG)
    seeded = 0
    if new_id is None:
        res = conn.execute(
            sa.insert(categories).values(
                slug=PROFESSIONAL_SERVICES_SLUG,
                name=PROFESSIONAL_SERVICES_NAME,
                sort_order=PROFESSIONAL_SERVICES_SORT,
            )
        )
        seeded = 1
        new_id = conn.execute(
            sa.select(categories.c.id).where(
                categories.c.slug == PROFESSIONAL_SERVICES_SLUG
            )
        ).scalar_one()

    old_id = slug_to_id.get(_LEGACY_PROFESSIONAL_SLUG)
    eligible = [providers.c.category_id.is_(None)]
    if old_id is not None:
        eligible.append(providers.c.category_id == old_id)
    res = conn.execute(
        sa.update(providers)
        .where(providers.c.primary_category == PROFESSIONAL_SERVICES_SLUG)
        .where(sa.or_(*eligible))
        .values(category_id=new_id)
    )
    return {"seeded": seeded, "repointed": res.rowcount or 0}


def reverse_professional_services(conn) -> None:
    """Undo: repoint rows back to the legacy bucket (when it exists, else NULL),
    then drop the canonical row."""
    import sqlalchemy as sa

    categories, providers = _tables_ps()
    slug_to_id = {
        r[0]: r[1] for r in conn.execute(sa.select(categories.c.slug, categories.c.id))
    }
    new_id = slug_to_id.get(PROFESSIONAL_SERVICES_SLUG)
    if new_id is None:
        return
    old_id = slug_to_id.get(_LEGACY_PROFESSIONAL_SLUG)
    conn.execute(
        sa.update(providers)
        .where(providers.c.category_id == new_id)
        .values(category_id=old_id)
    )
    conn.execute(
        sa.delete(categories).where(categories.c.slug == PROFESSIONAL_SERVICES_SLUG)
    )
