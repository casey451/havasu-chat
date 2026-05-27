"""Direction C category-pages module (PR D5).

Ships ``/categories/{slug}`` -- the destination for the D1 tab anchors and
the D4 service-tile hrefs. Co-exists with the older Phase 6.2
``/category/{slug}`` (singular) surface in ``app/api/routes/category_pages.py``
which uses the Entity / EntityCategory model. This module uses
``Provider.category`` legacy slug strings directly, matching D2/D3/D4's
data path.

Two route shapes share one router:

- **Mega-tabs** (4 routes) -- the home_c topbar tab destinations.
  Aggregate multiple ``Provider.category`` slugs into one page.
    eat-drink, on-the-water, things-to-do, services
- **Tile routes** (12 routes) -- the D4 ``_SERVICE_TILES`` hrefs.
  Each route filters on one ``Provider.category`` slug (or a small
  semantic group).

One route -- ``on-the-water`` -- appears in both lists; it renders the
mega-tab aggregation. Total unique routes: 15.
"""
