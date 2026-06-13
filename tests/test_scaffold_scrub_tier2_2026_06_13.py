"""P1-3 / P2-1: the grounding-scaffold scrub must also apply to Tier-2 LLM voices.

Prod leaked "Grocery options aren't listed in the provided rows" on a Tier-2 path;
the Tier-3 scrubber never ran there. scrub_scaffold_leak() is a lighter, reusable
scrub now called from tier2_formatter.postprocess.
"""

from __future__ import annotations

from app.chat.tier3_postprocess import scrub_scaffold_leak


def test_scrub_drops_scaffold_sentence_keeps_rest() -> None:
    text = (
        "Grocery options aren't listed in the provided rows. "
        "You can check local resources or visit golakehavasu.com."
    )
    out = scrub_scaffold_leak(text)
    assert "provided rows" not in out.lower()
    assert "local resources" in out


def test_scrub_entire_leak_returns_clean_fallback() -> None:
    out = scrub_scaffold_leak("That isn't in the provided rows.")
    assert "provided rows" not in out.lower()
    assert "/contribute" in out  # the clean honest-gap fallback


def test_scrub_leaves_clean_text_unchanged() -> None:
    text = "Here are three great spots in town."
    assert scrub_scaffold_leak(text) == text
