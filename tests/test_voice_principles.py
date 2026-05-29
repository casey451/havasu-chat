"""Voice prompt unification — byte-equivalence + helper contract.

Attests that compose_voice_prompt() reproduces each pre-refactor inlined
_SYSTEM_PROMPT verbatim (brand-contract attestation).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import patch

from app.chat.voice_principles import compose_voice_prompt, run_voice_llm
from app.home import pullquote

logger = logging.getLogger("test_voice_principles")

_LEGACY_DAY_AGENDA = (
    "You are Hava — the AI local of Lake Havasu City.\n\n"
    "VOICE (non-negotiable):\n"
    "* Speak AS THE LOCAL. Direct, declarative, no customer-service phrasing.\n"
    "* 1–2 short sentences. End every sentence with a period. NO question marks.\n"
    '* No customer-service phrasing: never "you might want to...",'
    ' "feel free to...", "I\'d be happy to...", "here are several options".\n'
    "* The structured listing renders BELOW your line — DO NOT enumerate items"
    " inline. Your job is the read on the day, not a roll call.\n"
    '* No Southwest climate-as-texture ("monsoon", "dry heat").\n'
    "* Optional: AT MOST ONE Markdown link `[name](url)`, only if you mention"
    " something specific from the catalog and the URL was provided. Never"
    " invent venues or URLs.\n\n"
    "OUTPUT: just Hava's read. No quotation marks, no preface, no signature."
)

_LEGACY_WEEK_STRIP = (
    "You are Hava — the AI local of Lake Havasu City.\n\n"
    "VOICE (non-negotiable):\n"
    "* Speak AS THE LOCAL. Direct, declarative, no customer-service phrasing.\n"
    "* 1–2 short sentences. End every sentence with a period. NO question marks.\n"
    "* You're describing the WEEK as a whole (N things across the week, busy"
    " days vs quiet ones, one or two stand-outs). The 7-day strip + selected-day"
    " agenda renders BELOW your line — DO NOT enumerate items inline.\n"
    "* No customer-service phrasing.\n"
    "* No Southwest climate-as-texture.\n"
    "* Optional: AT MOST ONE Markdown link `[name](url)`, only if you mention"
    " something specific from the catalog and the URL was provided.\n\n"
    "OUTPUT: just Hava's read. No quotation marks, no preface, no signature."
)

_LEGACY_CARD_ROW = (
    "You are Hava — the AI local of Lake Havasu City.\n\n"
    "VOICE (non-negotiable):\n"
    "* Speak AS THE LOCAL. Direct, declarative, no customer-service phrasing.\n"
    "* 1–2 short sentences. End every sentence with a period. NO question marks.\n"
    "* You're framing 2–3 hand-picked recommendations — give the read on the"
    " shape of the picks (e.g. 'Both lean upscale.' 'One waterfront, one"
    " patio.'). The cards render BELOW your line — DO NOT enumerate them"
    " inline. DO NOT list names.\n"
    "* No customer-service phrasing: never 'you might want to...', 'feel free"
    " to...', 'I'd be happy to...', 'here are several options'.\n"
    "* No Southwest climate-as-texture ('monsoon', 'dry heat').\n"
    "* Optional: AT MOST ONE Markdown link `[name](url)`, only if you mention"
    " something specific from the catalog and the URL was provided. Never"
    " invent venues or URLs.\n\n"
    "OUTPUT: just Hava's read. No quotation marks, no preface, no signature."
)

_LEGACY_SINGLE_CARD = (
    "You are Hava — the AI local of Lake Havasu City.\n\n"
    "VOICE (non-negotiable):\n"
    "* Speak AS THE LOCAL. Direct, declarative, no customer-service phrasing.\n"
    "* 1–2 short sentences. End every sentence with a period. NO question marks.\n"
    "* You're describing ONE THING (an event, a venue, or a business). The"
    " card with facts + actions renders BELOW your line — DO NOT enumerate"
    " hours, phone, address inline.\n"
    "* Lead with the why-it-matters / how-it-fits, not the what (the card"
    " shows the what).\n"
    "* No customer-service phrasing. No Southwest climate-as-texture.\n\n"
    "OUTPUT: just Hava's read. No quotation marks, no preface, no signature."
)


def test_compose_voice_prompt_day_agenda_matches_previous_inlined() -> None:
    assert compose_voice_prompt("day_agenda") == _LEGACY_DAY_AGENDA


def test_compose_voice_prompt_week_strip_matches_previous_inlined() -> None:
    assert compose_voice_prompt("week_strip") == _LEGACY_WEEK_STRIP


def test_compose_voice_prompt_card_row_matches_previous_inlined() -> None:
    assert compose_voice_prompt("card_row") == _LEGACY_CARD_ROW


def test_compose_voice_prompt_single_card_matches_previous_inlined() -> None:
    assert compose_voice_prompt("single_card") == _LEGACY_SINGLE_CARD


def test_compose_voice_prompt_single_business_card_matches_previous_inlined() -> None:
    assert compose_voice_prompt("single_business_card") == _LEGACY_SINGLE_CARD


def test_compose_voice_prompt_allow_link_false_drops_link_clause() -> None:
    prompt = compose_voice_prompt("day_agenda", allow_link=False)
    assert "Markdown link" not in prompt
    assert _LEGACY_DAY_AGENDA.replace(
        "* Optional: AT MOST ONE Markdown link `[name](url)`, only if you mention"
        " something specific from the catalog and the URL was provided. Never"
        " invent venues or URLs.\n\n",
        "\n",
    ) == prompt


def test_run_voice_llm_returns_fallback_on_exception() -> None:
    with patch(
        "app.chat.voice_principles.call_anthropic_messages",
        side_effect=RuntimeError("boom"),
    ):
        text, in_tok, out_tok = run_voice_llm(
            system_prompt="sys",
            user_text="user",
            fallback_text="fallback",
            logger=logger,
            surface="test",
        )
    assert (text, in_tok, out_tok) == ("fallback", 0, 0)


def test_run_voice_llm_returns_fallback_on_none_result() -> None:
    with patch(
        "app.chat.voice_principles.call_anthropic_messages",
        return_value=None,
    ):
        text, in_tok, out_tok = run_voice_llm(
            system_prompt="sys",
            user_text="user",
            fallback_text="fallback",
            logger=logger,
            surface="test",
        )
    assert (text, in_tok, out_tok) == ("fallback", 0, 0)


def test_run_voice_llm_strips_wrapping_smart_quotes() -> None:
    usage = SimpleNamespace(billable_input=11, output_tokens=7)
    result = SimpleNamespace(text="“Hello from Hava.”", usage=usage)
    with patch(
        "app.chat.voice_principles.call_anthropic_messages",
        return_value=result,
    ):
        text, in_tok, out_tok = run_voice_llm(
            system_prompt="sys",
            user_text="user",
            fallback_text="fallback",
            logger=logger,
            surface="test",
        )
    assert text == "Hello from Hava."
    assert in_tok == 11 and out_tok == 7


def test_run_voice_llm_rejects_question_mark() -> None:
    usage = SimpleNamespace(billable_input=5, output_tokens=3)
    result = SimpleNamespace(text="Want to go?", usage=usage)
    with patch(
        "app.chat.voice_principles.call_anthropic_messages",
        return_value=result,
    ):
        text, in_tok, out_tok = run_voice_llm(
            system_prompt="sys",
            user_text="user",
            fallback_text="fallback",
            logger=logger,
            surface="test",
        )
    assert text == "fallback"
    assert in_tok == 5 and out_tok == 3


def test_run_voice_llm_rejects_over_280_chars() -> None:
    usage = SimpleNamespace(billable_input=9, output_tokens=40)
    long_text = "x" * 300
    result = SimpleNamespace(text=long_text, usage=usage)
    with patch(
        "app.chat.voice_principles.call_anthropic_messages",
        return_value=result,
    ):
        text, in_tok, out_tok = run_voice_llm(
            system_prompt="sys",
            user_text="user",
            fallback_text="fallback",
            logger=logger,
            surface="test",
        )
    assert text == "fallback"
    assert in_tok == 9 and out_tok == 40


def test_pullquote_extras_line_present() -> None:
    assert "fact-free atmospheric prose" in pullquote._VOICE_PROMPT
    assert pullquote._VOICE_PROMPT.startswith(compose_voice_prompt("pullquote"))
