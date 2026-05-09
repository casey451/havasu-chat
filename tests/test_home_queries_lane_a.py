"""Unit tests for Lane A of the UI-data-correctness pass:

- Fix #2: ``_category_label`` and the contract that builders never leak
  raw ``Provider.category`` slugs into the surface.
- Fix #4: ``_card_blurb`` sanitizer hardening — labelled-field strip,
  trailing-fragment trim, venue+date fallback for Event-shaped records.

Per docs/maintainability/ui_data_correctness_spec.md §2.4 and §4.4.

Tests Fix #1 (``tonight()``) and Fix #3 (``_format_phone`` placeholder
guard) live in their own modules — see Lane B and Lane C in the spec.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.home.queries import (
    CATEGORY_LABELS,
    _card_blurb,
    _category_label,
)

# ─────────── Fix #2 — _category_label ───────────


def test_category_label_known_slug() -> None:
    assert _category_label("home_services") == "Home services"


def test_category_label_known_slug_compound() -> None:
    assert _category_label("religion_community") == "Community"


def test_category_label_widened_set_real_estate() -> None:
    """The widened map covers Provider.category values that previously
    fell through to a title-cased slug. Real estate is the canonical
    example because the title-case fallback ('Real Estate') reads worse
    than the sentence-case label ('Real estate')."""
    assert _category_label("real_estate") == "Real estate"


def test_category_label_widened_set_general_contractor() -> None:
    assert _category_label("general_contractor") == "Contractors"


def test_category_label_unknown_slug_uses_capitalize_not_title() -> None:
    """Defensive fallback for any unmapped slug. We use ``capitalize`` not
    ``title`` so multi-word slugs read like prose ('Frobnicator service'
    not 'Frobnicator Service')."""
    assert _category_label("frobnicator_service") == "Frobnicator service"


def test_category_label_empty_returns_local_pro() -> None:
    assert _category_label(None) == "Local pro"
    assert _category_label("") == "Local pro"


def test_category_label_map_has_widened_entries() -> None:
    """Lock the widened set in place so a future deletion is a deliberate
    decision rather than an accidental regression."""
    widened = {
        "general_contractor",
        "real_estate",
        "insurance",
        "financial",
        "legal",
        "event_venue",
        "lodging",
        "tourism",
        "education",
        "pet",
        "boat_repair",
        "boat_rental",
    }
    assert widened.issubset(set(CATEGORY_LABELS.keys()))


# ─────────── Fix #4 — _card_blurb sanitizer hardening ───────────


def _ev(
    description: str = "",
    summary: str | None = None,
    location_name: str | None = None,
    ev_date: date | None = None,
) -> SimpleNamespace:
    """Build an event-shaped duck-typed record for blurb tests.

    ``_card_blurb`` reads only ``summary``, ``description``, ``location_name``,
    and ``date`` — duck-typing keeps these tests fast and DB-free.
    """
    return SimpleNamespace(
        summary=summary,
        description=description,
        location_name=location_name,
        date=ev_date,
    )


def test_card_blurb_passes_real_description() -> None:
    """Sanity check: a normal sentence comes through unchanged (modulo
    trailing period, which the existing splitter already strips)."""
    out = _card_blurb(_ev(description="Live music on the patio Saturday night."))
    assert out == "Live music on the patio Saturday night"


def test_card_blurb_strips_labelled_fields_keeps_real_sentence() -> None:
    """Lines that start with Date:/Venue:/etc. are UI scaffolding from a
    scraper export — strip them before the URL pass."""
    raw = (
        "Date: May 9, 2026\n"
        "Venue: McCulloch Plaza\n"
        "Organizer: Havasu Together\n"
        "A real sentence about the event."
    )
    out = _card_blurb(_ev(description=raw))
    assert out == "A real sentence about the event"


def test_card_blurb_csv_dump_falls_back_to_venue_date() -> None:
    """When the entire description is labelled-field junk, sanitization
    leaves nothing — fall back to a venue+date sentence rather than emit
    an empty blurb."""
    raw = (
        "Date: May 9, 2026\n"
        "Time: 12:00 – 12:00\n"
        "Venue: 2144 McCulloch Blvd N\n"
        "Organizer: Havasu Together\n"
        "Categories: Farmer's Market"
    )
    out = _card_blurb(
        _ev(
            description=raw,
            location_name="McCulloch Plaza",
            ev_date=date(2026, 5, 9),
        )
    )
    assert out == "At McCulloch Plaza on May 9"


def test_card_blurb_strips_full_url() -> None:
    """The original URL strip already handled this — confirm the widened
    regex doesn't regress legitimate URL stripping."""
    raw = "See full schedule at https://www.lhcaz.gov/parks-recreation/open-swim-schedule"
    out = _card_blurb(_ev(description=raw))
    assert "https://" not in out
    assert "lhcaz.gov" not in out


def test_card_blurb_strips_bare_domain_url() -> None:
    """Widened URL regex catches descriptions that lost their http:// prefix
    in upstream copy-paste/CMS roundtrip."""
    raw = "More info at lhcaz.gov/parks-recreation/open-swim-schedule"
    out = _card_blurb(_ev(description=raw))
    assert "lhcaz.gov" not in out


def test_card_blurb_strips_www_prefix_url() -> None:
    raw = "Tickets at www.havasuevents.com/tickets"
    out = _card_blurb(_ev(description=raw))
    assert "havasuevents.com" not in out
    assert "www." not in out


def test_card_blurb_summary_short_circuit_unchanged() -> None:
    """When ``summary`` is set, sanitization is bypassed entirely — that's
    the editorial-curated path. Confirm it still wins over description."""
    out = _card_blurb(
        _ev(
            summary="Hava-curated blurb.",
            description="Date: foo\nThis should never appear.",
        )
    )
    assert out == "Hava-curated blurb."


def test_card_blurb_empty_record_no_fallback_data() -> None:
    """Provider-shaped records (no ``location_name`` / ``date``) with empty
    descriptions return empty string. Card template handles the empty
    blurb gracefully."""
    out = _card_blurb(_ev(description=""))
    assert out == ""


def test_card_blurb_truncates_at_140() -> None:
    """Long sentences truncate at 140 chars on a word boundary with an
    ellipsis. Existing behavior — confirm not regressed."""
    long_sentence = "This is a very long blurb " * 20
    out = _card_blurb(_ev(description=long_sentence))
    assert len(out) <= 140
    assert out.endswith("…")


def test_card_blurb_no_double_space_after_url_strip() -> None:
    """Whitespace-collapse pass should leave at most single spaces between
    surviving tokens, even after URL/label removal punches holes."""
    raw = "Visit https://example.com today for details https://example.com/more."
    out = _card_blurb(_ev(description=raw))
    assert "  " not in out
