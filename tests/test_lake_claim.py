"""Phase 4b — Lake Ink & Brass claim + merchant-upgrade surfaces.

All four pages are auth-gated (claim requires a logged-in user; merchant upgrade
requires a *verified* claim), so the templates are rendered directly with sample
context — the established Phase-3 pattern. Each is asserted noindex, structurally
WCAG-clean (_A11yChecker), single-h1, and carrying its real POST contract. These
are lead-capture flows — no payment is taken — so there is nothing billing to
assert, only that the forms keep their field names + actions.
"""

from __future__ import annotations

from starlette.requests import Request
from test_ada_compliance import _A11yChecker

from app.auth.routes import templates as _auth_templates
from app.main import app


def _req(path: str) -> Request:
    return Request({
        "type": "http", "method": "GET", "path": path, "raw_path": path.encode(),
        "query_string": b"", "headers": [(b"host", b"testserver")], "scheme": "http",
        "server": ("testserver", 80), "client": ("test", 1), "app": app,
    })


def _render(name: str, path: str, **ctx: object) -> str:
    return _auth_templates.env.get_template(name).render(request=_req(path), **ctx)


def _a11y(html: str) -> list[str]:
    checker = _A11yChecker()
    checker.feed(html)
    return checker.finish()


class _FakeEntity:
    name = "Barley Brothers"
    slug = "barley-brothers"


class _FakeClaim:
    def __init__(self, status: str, rejection_reason: str | None = None) -> None:
        self.status = status
        self.rejection_reason = rejection_reason


# ── claim form ──────────────────────────────────────────────────────────────

def test_lake_claim_form() -> None:
    b = _render("claim_form_lake.html", "/claim/barley-brothers", entity=_FakeEntity())
    assert 'data-theme="lake"' in b
    assert 'name="robots" content="noindex"' in b
    assert 'action="/claim/barley-brothers"' in b
    assert 'name="notes"' in b and 'id="notes"' in b  # labeled optional notes field
    assert "Barley Brothers" in b
    assert b.count("<h1") == 1
    assert not _a11y(b)


# ── claim status (all branches) ─────────────────────────────────────────────

def test_lake_claim_status_branches() -> None:
    for status, badge in (("pending", "Pending review"), ("verified", "Verified"),
                          ("rejected", "Rejected")):
        b = _render("claim_status_lake.html", "/claim/barley-brothers",
                    entity=_FakeEntity(), claim=_FakeClaim(status))
        assert 'data-theme="lake"' in b
        assert 'name="robots" content="noindex"' in b
        assert badge in b
        assert b.count("<h1") == 1
        assert not _a11y(b)

    # rejection reason surfaces only on the rejected branch
    rejected = _render("claim_status_lake.html", "/claim/barley-brothers",
                       entity=_FakeEntity(),
                       claim=_FakeClaim("rejected", "Could not verify ownership."))
    assert "Could not verify ownership." in rejected
    assert not _a11y(rejected)


# ── claim submitted ─────────────────────────────────────────────────────────

def test_lake_claim_submitted() -> None:
    b = _render("claim_submitted_lake.html", "/claim/barley-brothers", entity=_FakeEntity())
    assert 'data-theme="lake"' in b
    assert 'name="robots" content="noindex"' in b
    assert 'href="/account"' in b
    assert "Barley Brothers" in b
    assert b.count("<h1") == 1
    assert not _a11y(b)


# ── merchant upgrade (form + pending banner) ────────────────────────────────

def test_lake_merchant_upgrade_form() -> None:
    b = _render("merchant_upgrade_form_lake.html", "/merchant/upgrade/barley-brothers",
                entity=_FakeEntity(), slots=["marquee", "spotlight", "promoted"],
                pending=False)
    assert 'data-theme="lake"' in b
    assert 'name="robots" content="noindex"' in b
    assert 'action="/merchant/upgrade/barley-brothers"' in b
    assert 'name="requested_slot"' in b and 'id="requested_slot"' in b  # labeled select
    assert 'name="message"' in b and 'id="message"' in b  # labeled textarea
    assert 'value="marquee"' in b  # slot values preserved verbatim for the POST
    assert "no payment is collected on this page" in b  # honest, no billing here
    assert b.count("<h1") == 1
    assert not _a11y(b)


def test_lake_merchant_upgrade_pending() -> None:
    b = _render("merchant_upgrade_form_lake.html", "/merchant/upgrade/barley-brothers",
                entity=_FakeEntity(), slots=["marquee", "spotlight"], pending=True)
    assert "request to feature this listing has been received" in b
    assert 'name="requested_slot"' not in b  # form hidden while a request is pending
    assert b.count("<h1") == 1
    assert not _a11y(b)
