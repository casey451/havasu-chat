"""Unified admin portal (isolated, unwired).

This package is intentionally imported by nothing in the running app.
See README.md in this directory for the two-line wiring change that
activates it, and docs/ADMIN_PORTAL_PLAN.md for the full plan.

No import-time side effects beyond module definition; no registration
against app.main, no shared-metadata models, no applied migrations.
"""
