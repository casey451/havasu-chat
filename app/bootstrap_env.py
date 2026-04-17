"""Load local `.env` once without clobbering platform-injected variables (Railway, CI, etc.)."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# Project root = parent of `app/`
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DOTENV_PATH = _PROJECT_ROOT / ".env"
_LOADED = False


def ensure_dotenv_loaded() -> None:
    """Parse `.env` if present. Existing ``os.environ`` keys are never overwritten."""
    global _LOADED
    if _LOADED:
        return
    load_dotenv(dotenv_path=_DOTENV_PATH, override=False)
    _LOADED = True
