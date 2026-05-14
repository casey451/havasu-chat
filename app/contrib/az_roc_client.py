"""Arizona Registrar of Contractors (AZ ROC) lookup helper (Phase 5).

The public search UI is Salesforce Experience Cloud; results are not
reliably present in the initial HTML shell. :func:`lookup_contractor`
returns ``None`` until a Playwright-based or reverse-engineered XHR path
lands — callers (``scripts/az_roc_verify.py``) treat ``None`` as *no match*.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class AzRocMatch:
    license_number: str
    classification: str | None
    status: str | None
    raw: dict[str, Any] | None = None


def lookup_contractor(
    client: httpx.Client,
    business_name: str,
    *,
    search_url: str = "https://azroc.my.site.com/AZRoc/s/contractor-search",
) -> AzRocMatch | None:
    """Best-effort contractor lookup. **v1 always returns ``None``** (no HTML/XHR parse)."""
    _ = (client, business_name, search_url)
    return None
