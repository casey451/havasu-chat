"""Casual, friendly user-facing strings (Phase 7)."""

# Greeting (idle sessions only)
GREETING_REPLY = (
    "Hey! I can help you find what's going on around town, or add an event if you're hosting — what sounds good?"
)

# When intent is unclear
UNCLEAR_REPLY = (
    "Hmm, not sure what you mean — are you looking for something to do, or adding an event?"
)

# User bails / restarts
CANCEL_REPLY = "No worries! What can I help you find?"

# User said no at confirmation — fixup
REJECTION_FIX = "No prob — what should we change?"

# Event saved live
ADDED_LIVE = "You're all set — it's live 🎉"

# Duplicate check (use .format(title=...))
DUPLICATE_PROMPT = "Heads up — this looks a lot like {title}. Same one?"

# Confirmed duplicate — merge flow
MERGE_FOLLOWUP = (
    "Cool — that's {title} on {date} at {time}, at {location}. Want to tack on anything that's missing?"
)

# Kept existing on merge decline
MERGE_KEPT = "Got it — I left the original event as-is."

# After merge with updates
MERGE_UPDATED = "Nice — I folded that into {title} for you."

# Preview before confirm
def preview_event_line(title: str, date_s: str, time_s: str, loc: str) -> str:
    return (
        f"So I've got: {title}, {date_s}, {time_s}, at {loc}. Sound right?"
    )

# Search
SEARCH_EMPTY = "Nothing yet! You can add one by telling me the details."

SEARCH_INTRO_MANY = "Here's what I found:"

# Missing-field fallback (should be rare)
MISSING_FIELD_GLITCH = "Whoops — I lost track for a second. Mind starting that event again from the top?"

# Generic soft recovery (exceptions)
CHAT_SOFT_FAIL = "Something went wrong on my end, try again?"

STALE_SESSION_REPLY = (
    "It's been a few minutes, so I cleared where we left off. What would you like to do next?"
)

# Phase 8.5 — search / intent rewrite
GREETING_MID_SEARCH = "Hey! Still looking for something, or did you want to change gears?"

CLARIFY_DATE = "When are you thinking — today, this weekend, next week?"

CLARIFY_ACTIVITY = "What kind of thing — sports, arts, something else?"

LISTING_NUDGE_NONE = "Want to tighten it? Tell me a day or a vibe."

LISTING_NUDGE_DATE_SET = "Want to narrow by type? Sports, arts, kids stuff?"

LISTING_NUDGE_ACTIVITY_SET = "Want to narrow by day? This weekend, next week?"

NOTHING_IN_RANGE = "Nothing on for that time. Want to peek at what's coming up later?"

NOTHING_FOR_ACTIVITY = "No {activity} events on right now. Want me to broaden the search?"

SOFT_CANCEL_REPLY = "All good — what would you like to do?"

HARD_RESET_REPLY = "Fresh start. What are you looking for?"

ESCAPE_HATCH_REPLY = "Got it — switching gears. What are you trying to do?"

SERVICE_STUB_REPLY = (
    "I focus on what's happening around town — events, classes, and activities. "
    "Want me to find something for a day you're free?"
)

DEAL_STUB_REPLY = (
    "I don't have local deals in here yet — but I can help you find something fun going on. "
    "What day works for you?"
)
