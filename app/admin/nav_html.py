"""Shared inline nav for Phase 5 admin HTML pages (handoff §2.8 — string HTML, no Jinja2)."""


def admin_phase5_nav_html() -> str:
    """Return the standard ``<nav class="nav">`` block (identical on all modules)."""
    return """    <nav class="nav">
      <a href="/admin/overview">Dashboard</a>
      <a href="/admin?tab=queue">Events</a>
      <a href="/admin/jobs">Jobs</a>
      <a href="/admin/contributions">Contributions</a>
      <a href="/admin/mentioned-entities">Mentioned entities</a>
      <a href="/admin/categories">Categories</a>
      <a href="/admin/providers/miscategorized">Miscategorized</a>
      <a href="/admin/analytics">Analytics</a>
      <a href="/admin/feedback">Feedback</a>
    </nav>"""
