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
SEARCH_EMPTY = "Nothing on the list yet — want to add one? Just tell me the details."

SEARCH_INTRO_MANY = "Here's what I found:"

# Missing-field fallback (should be rare)
MISSING_FIELD_GLITCH = "Whoops — I lost track for a second. Mind starting that event again from the top?"

# Generic soft recovery (exceptions)
CHAT_SOFT_FAIL = "Hmm, something got tangled on my end — mind saying that again?"
