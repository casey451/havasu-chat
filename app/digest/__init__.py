"""Phase A3: "This weekend in Havasu" weekend digest.

Self-contained package, deliberately disjoint from ``app.alerts.*``. Builds a
per-user weekend digest (events this weekend + events at the user's saved /
followed venues), renders an email body, and offers a DRY-RUN path that builds
and renders WITHOUT sending. Actual send cadence/cron is a flagged Casey
product decision and is intentionally not wired here.
"""
