"""Unit tests for ``app.core.provider_name.clean_name`` (CLUSTER-08 name hygiene).

The helper strips vendor marketing tails — everything from the first ``|``
character onward, including a trailing whitespace run. Used both as a Jinja
filter (registered in ``app/main.py``) and on the chat ``build_business_list``
server path so the rendered surfaces and the API payload agree.
"""

from __future__ import annotations

from app.core.provider_name import clean_name


def test_clean_name_returns_empty_for_none() -> None:
    assert clean_name(None) == ""


def test_clean_name_returns_empty_for_empty_string() -> None:
    assert clean_name("") == ""


def test_clean_name_passes_through_when_no_pipe() -> None:
    assert clean_name("Acme Plumbing") == "Acme Plumbing"


def test_clean_name_strips_basic_pipe_tail() -> None:
    assert (
        clean_name("Havasu Hills Apartment Homes | An AllThrive 365 Property")
        == "Havasu Hills Apartment Homes"
    )


def test_clean_name_handles_pipe_with_no_tail() -> None:
    # Pipe at the very end — head is the whole prefix, trailing space trimmed.
    assert clean_name("Acme Plumbing |") == "Acme Plumbing"


def test_clean_name_strips_trailing_whitespace_before_pipe() -> None:
    assert clean_name("Acme Plumbing   | Branded Vendor Stuff") == "Acme Plumbing"


def test_clean_name_splits_on_first_pipe_only() -> None:
    # Multiple pipes — only the head before the FIRST pipe survives.
    assert clean_name("First Name | Second | Third") == "First Name"


def test_clean_name_is_idempotent() -> None:
    dirty = "Havasu Hills Apartment Homes | An AllThrive 365 Property"
    once = clean_name(dirty)
    twice = clean_name(once)
    assert once == twice
    assert twice == "Havasu Hills Apartment Homes"


def test_clean_name_does_not_lstrip_leading_whitespace() -> None:
    # The contract is rstrip only — leading whitespace is the caller's problem
    # (and is uncommon in practice). Document via test.
    assert clean_name("  Acme | tail") == "  Acme"
