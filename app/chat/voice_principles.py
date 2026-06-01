"""Voice principles — single source for Hava's chat voice prompts.

This module owns the *system prompts* sent to the LLM for Tier 2
componentized voice generation (day_agenda, week_strip, card_row,
single_card, single_business_card) and home/pullquote.py. It does NOT
own Tier 3's prompt — that lives at prompts/system_prompt.txt and is
loaded verbatim to preserve Anthropic prompt-cache behavior. See
TIER3_PROMPT_PATH and the Tier 3 boundary note in tier3_handler.py.

Canonical brand source of truth: BUILD.md "Voice principles
(non-negotiable)" (lines 19–33). When the brand rules drift, edit them
in BUILD.md first, then mirror to the constants in this module.

This module also owns the shared LLM-call helper run_voice_llm() that
implements the SWR fallback discipline used by every Tier 2 voice
generator: LLM call → strip wrapping quotes → voice-rule guards
(no '?', <=280 chars) → deterministic fallback on any failure or
guard violation. The voice-rule guards are part of the brand contract
and belong here, not in per-builder modules.
"""

from __future__ import annotations

import logging
from typing import Literal

from app.core.llm_messages import call_anthropic_messages

# Path the Tier 3 handler loads via app.core.llm_messages.load_prompt.
# Documented here so a code search for voice surfaces finds Tier 3 too.
TIER3_PROMPT_PATH = "prompts/system_prompt.txt"

VoiceKind = Literal[
    "day_agenda",
    "week_strip",
    "card_row",
    "single_card",
    "single_business_card",
    "pullquote",
]

_PERSONA = "You are Hava — the AI local of Lake Havasu City."

_VOICE_HEADER = "VOICE (non-negotiable):"

_SPEAK_AS_LOCAL = "* Speak AS THE LOCAL. Direct, declarative, no customer-service phrasing."

_ONE_TO_TWO_SENTENCES = (
    "* 1–2 short sentences. End every sentence with a period. NO question marks."
)

_CUSTOMER_SERVICE_FULL_DOUBLE = (
    '* No customer-service phrasing: never "you might want to...",'
    ' "feel free to...", "I\'d be happy to...", "here are several options".'
)

_CUSTOMER_SERVICE_FULL_SINGLE = (
    "* No customer-service phrasing: never 'you might want to...', 'feel free"
    " to...', 'I'd be happy to...', 'here are several options'."
)

_CUSTOMER_SERVICE_ABBREV = "* No customer-service phrasing."

_CLIMATE_FULL_DOUBLE = '* No Southwest climate-as-texture ("monsoon", "dry heat").'

_CLIMATE_FULL_SINGLE = "* No Southwest climate-as-texture ('monsoon', 'dry heat')."

_CLIMATE_ABBREV = "* No Southwest climate-as-texture."

_LINK_CLAUSE_FULL = (
    "* Optional: AT MOST ONE Markdown link `[name](url)`, only if you mention"
    " something specific from the catalog and the URL was provided. Never"
    " invent venues or URLs."
)

_LINK_CLAUSE_SHORT = (
    "* Optional: AT MOST ONE Markdown link `[name](url)`, only if you mention"
    " something specific from the catalog and the URL was provided."
)

_OUTPUT_FOOTER = "OUTPUT: just Hava's read. No quotation marks, no preface, no signature."

_COMPONENT_FRAMING: dict[VoiceKind, str] = {
    "day_agenda": (
        "* The structured listing renders BELOW your line — DO NOT enumerate"
        " items inline. Your job is the read on the day, not a roll call."
    ),
    "week_strip": (
        "* You're describing the WEEK as a whole (N things across the week,"
        " busy days vs quiet ones, one or two stand-outs). The 7-day strip +"
        " selected-day agenda renders BELOW your line — DO NOT enumerate"
        " items inline."
    ),
    "card_row": (
        "* You're framing 2–3 hand-picked recommendations — give the read on"
        " the shape of the picks (e.g. 'Both lean upscale.' 'One waterfront,"
        " one patio.'). The cards render BELOW your line — DO NOT enumerate"
        " them inline. DO NOT list names."
    ),
    "single_card": (
        "* You're describing ONE THING (an event, a venue, or a business). The"
        " card with facts + actions renders BELOW your line — DO NOT enumerate"
        " hours, phone, address inline.\n"
        "* Lead with the why-it-matters / how-it-fits, not the what (the card"
        " shows the what).\n"
        "* No customer-service phrasing. No Southwest climate-as-texture."
    ),
    "single_business_card": (
        "* You're describing ONE THING (an event, a venue, or a business). The"
        " card with facts + actions renders BELOW your line — DO NOT enumerate"
        " hours, phone, address inline.\n"
        "* Lead with the why-it-matters / how-it-fits, not the what (the card"
        " shows the what).\n"
        "* No customer-service phrasing. No Southwest climate-as-texture."
    ),
    "pullquote": (
        "* Speak AS THE LOCAL. Direct, declarative, never customer-service.\n"
        "* 1–3 short sentences. End every sentence with a period. NO question marks.\n"
        '* No customer-service phrasing: never "you might want to...", "feel free to...",\n'
        "  \"I'd be happy to...\". Hava doesn't offer; she observes.\n"
        '* No Southwest climate-as-texture: don\'t say "monsoon," "dry heat," "before\n'
        '  it gets too hot." Temperature is fine when factually relevant.\n'
        "* Optional: include AT MOST ONE Markdown link, in the form `[name](url)`,\n"
        "  pointing at a catalog item from the candidates list below. Never invent\n"
        "  a venue name or URL."
    ),
}

_PULLQUOTE_PERSONA = (
    "You are Hava — the AI local of Lake Havasu City. Write a single\n"
    'short pullquote, "Hava\'s read on tonight."'
)


def compose_voice_prompt(kind: VoiceKind, *, allow_link: bool = True) -> str:
    """Build the system prompt for a given component voice surface.

    Stanzas: persona, VOICE header, universal rules, component framing,
    optional link clause, OUTPUT footer. Composition is deterministic;
    test asserts byte-equivalence against the existing inlined prompts.
    """
    if kind == "pullquote":
        parts = [
            _PULLQUOTE_PERSONA,
            "",
            _VOICE_HEADER,
            _COMPONENT_FRAMING["pullquote"],
        ]
        return "\n".join(parts)

    if kind == "day_agenda":
        rule_lines = [
            _SPEAK_AS_LOCAL,
            _ONE_TO_TWO_SENTENCES,
            _CUSTOMER_SERVICE_FULL_DOUBLE,
            _COMPONENT_FRAMING["day_agenda"],
            _CLIMATE_FULL_DOUBLE,
        ]
        link = _LINK_CLAUSE_FULL if allow_link else None
        footer = _OUTPUT_FOOTER
    elif kind == "week_strip":
        rule_lines = [
            _SPEAK_AS_LOCAL,
            _ONE_TO_TWO_SENTENCES,
            _COMPONENT_FRAMING["week_strip"],
            _CUSTOMER_SERVICE_ABBREV,
            _CLIMATE_ABBREV,
        ]
        link = _LINK_CLAUSE_SHORT if allow_link else None
        footer = _OUTPUT_FOOTER
    elif kind == "card_row":
        rule_lines = [
            _SPEAK_AS_LOCAL,
            _ONE_TO_TWO_SENTENCES,
            _COMPONENT_FRAMING["card_row"],
            _CUSTOMER_SERVICE_FULL_SINGLE,
            _CLIMATE_FULL_SINGLE,
        ]
        link = _LINK_CLAUSE_FULL if allow_link else None
        footer = _OUTPUT_FOOTER
    elif kind in ("single_card", "single_business_card"):
        rule_lines = [
            _SPEAK_AS_LOCAL,
            _ONE_TO_TWO_SENTENCES,
            _COMPONENT_FRAMING[kind],
        ]
        link = None
        footer = _OUTPUT_FOOTER
    else:
        raise ValueError(f"unknown voice kind: {kind!r}")

    parts = [_PERSONA, "", _VOICE_HEADER, *rule_lines]
    if link:
        parts.append(link)
    parts.extend(["", footer])
    return "\n".join(parts)


def run_voice_llm(
    *,
    system_prompt: str,
    user_text: str,
    fallback_text: str,
    logger: logging.Logger,
    surface: str,
    max_tokens: int = 120,
    temperature: float = 0.5,
) -> tuple[str, int, int]:
    """Run the voice LLM with shared SWR fallback discipline.

    Returns (text, input_tokens, output_tokens). Token counts are 0 when
    the fallback was used (no successful LLM call). Voice-rule guards
    apply unconditionally — see BUILD.md §"Voice principles".
    """
    try:
        result = call_anthropic_messages(
            system_prompt=system_prompt,
            user_text=user_text,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception:
        logger.exception("%s: voice LLM raised; using fallback", surface)
        return fallback_text, 0, 0

    if result is None or not (result.text or "").strip():
        return fallback_text, 0, 0

    text = result.text.strip()
    if (
        text.startswith(('"', "'", "“", "”"))
        and text.endswith(('"', "'", "“", "”"))
        and len(text) > 1
    ):
        text = text[1:-1].strip()

    in_tok = result.usage.billable_input or 0
    out_tok = result.usage.output_tokens or 0

    if "?" in text:
        logger.warning("%s: voice contained '?'; using fallback", surface)
        return fallback_text, in_tok, out_tok
    if len(text) > 280:
        logger.warning("%s: voice too long; using fallback", surface)
        return fallback_text, in_tok, out_tok

    return text, in_tok, out_tok
