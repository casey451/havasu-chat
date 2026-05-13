"""``app.db`` package init — drives the Phase 1D dual-write hook registration.

This is the only place hook registration belongs because both
``app.db.models`` and ``app.db.entity_dual_write`` need to be fully loaded
before the registration can succeed, and they reference each other:
``entity_dual_write`` imports ORM classes from ``models`` at its top, and
``models`` (via Phase 1D dual-write) depends on ``entity_dual_write``'s
``register_catalog_dual_write_hooks`` function. Placing the registration
inside either module creates a partially-initialized-module cycle that
fails differently depending on which entry point loads first
(``database`` first, ``models`` first, ``entity_dual_write`` first).

Putting it in ``__init__.py`` resolves this cleanly: Python guarantees the
parent package's ``__init__.py`` runs before any of its submodules are
populated, so the import statement below drives the full load order
(``__init__.py → entity_dual_write → models → database → models finished
→ entity_dual_write finished → __init__.py calls hook``). After this
file finishes, *every* ``app.db.*`` import lands a fully-initialized
``app.db.models`` and a registered before_flush hook.

History — Session-22 (2026-05-13):
- Pre-fix: ``app/db/database.py`` module-top called ``_register_orm_listeners()``
  which force-loaded ``models`` then imported ``entity_dual_write``. That
  worked when uvicorn entry-point loaded ``models`` first but broke when
  ``scripts/parks_rec_load.py`` reached ``contribution_store -> models ->
  database`` first (models still loading when database tried to import
  entity_dual_write → ImportError: cannot import name 'ContactPoint').
- First attempted fix: moved hook registration to end of ``models.py``.
  That broke a different path — anything importing ``entity_dual_write``
  directly (including ``tests/test_phase1d_dual_write.py``) reached
  ``entity_dual_write -> models -> entity_dual_write`` cycle.
- Final fix (this file): centralize hook registration in package
  ``__init__.py`` so neither leaf module has the cycle-creating import.
"""

from app.db.entity_dual_write import register_catalog_dual_write_hooks

register_catalog_dual_write_hooks()
