from __future__ import annotations


ADD_EVENT_KEYWORDS = ["add", "there is", "i'm hosting", "im hosting", "event", "camp", "workshop", "clinic"]

# Must win over ADD_EVENT_KEYWORDS (e.g. "event" in "show me all events").
FORCE_SEARCH_PHRASES = (
    "show me all events",
    "what events do you have",
    "show me everything",
    "what's in the system",
    "whats in the system",
    "what is in the system",
    "in your system",
    "all events next week",
    "show me events",
    "what events are",
    "what events is",
    "list all events",
    "all upcoming events",
    "everything going on",
    "what's going on",
    "whats going on",
    "what is going on",
)

SEARCH_KEYWORDS = ["what", "anything", "looking for", "going on", "something", "find", "this weekend", "next week"]
CONFIRMATION_PHRASES = ["yes", "yep", "correct", "looks good", "that's right", "thats right"]
REJECTION_PHRASES = ["no", "nope", "not quite", "incorrect", "wrong"]

CANCEL_PHRASES = [
    "never mind",
    "nevermind",
    "start over",
    "forget it",
    "actually never mind",
    "scratch that",
    "nvm",
]

GREETING_TOKENS = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "yo",
        "sup",
        "hiya",
        "howdy",
        "morning",
        "evening",
        "good morning",
        "good afternoon",
        "good evening",
        "hi there",
        "hey there",
        "hello there",
    }
)


def detect_intent(message: str) -> str:
    msg = message.lower()
    if any(phrase in msg for phrase in FORCE_SEARCH_PHRASES):
        return "SEARCH_EVENTS"
    if any(keyword in msg for keyword in ADD_EVENT_KEYWORDS):
        return "ADD_EVENT"
    if any(keyword in msg for keyword in SEARCH_KEYWORDS):
        return "SEARCH_EVENTS"
    return "UNCLEAR"


def is_confirmation(message: str) -> bool:
    msg = message.lower().strip()
    return any(phrase in msg for phrase in CONFIRMATION_PHRASES)


def is_rejection(message: str) -> bool:
    msg = message.lower().strip()
    return any(phrase in msg for phrase in REJECTION_PHRASES)


def is_cancel_or_restart(message: str) -> bool:
    msg = message.lower().strip()
    return any(phrase in msg for phrase in CANCEL_PHRASES)


SKIP_OPTIONAL_CONTACT_PHRASES = (
    "skip",
    "no thanks",
    "none",
    "n/a",
    "nothing",
    "not needed",
    "pass",
)


def is_skip_optional_contact(message: str) -> bool:
    msg = message.lower().strip()
    if is_rejection(message):
        return True
    return any(p in msg for p in SKIP_OPTIONAL_CONTACT_PHRASES)


def is_greeting(message: str) -> bool:
    m = message.lower().strip().rstrip("!?")
    if not m:
        return False
    if m in GREETING_TOKENS:
        return True
    parts = m.split()
    if len(parts) <= 3 and parts[0] in ("hi", "hello", "hey") and len(m) <= 32:
        return True
    return False
