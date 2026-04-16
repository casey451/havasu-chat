"""slowapi limiter shared across FastAPI routes (Phase B)."""

from slowapi import Limiter
from slowapi.util import get_remote_address

RATE_LIMIT_MESSAGE = "Slow down a sec! Try again in a minute 😅"

limiter = Limiter(key_func=get_remote_address)
