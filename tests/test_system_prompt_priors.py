"""§5: the Tier-3 system prompt carries the condensed demographic/local ranking
priors — and only the *ranking* priors, so it does not contradict the existing
no-follow-up-questions rule."""

from __future__ import annotations

from app.core.llm_messages import load_prompt


def test_priors_block_present_in_tier3_system_prompt() -> None:
    prompt = load_prompt("system_prompt")
    assert "Demographic & local priors" in prompt
    assert "ranking bias only" in prompt
    assert "water town" in prompt  # the Lake Havasu local lean


def test_priors_do_not_introduce_clarifying_questions() -> None:
    prompt = load_prompt("system_prompt")
    # The no-questions hard rule must remain intact; the injected priors are
    # ranking-only and must not reintroduce a "ask a clarifying question" policy.
    assert "follow-up questions" in prompt
    assert "never spoken, never rules" in prompt
