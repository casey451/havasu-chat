"""Read-only extract of Tier 3 ``chat_logs`` rows (last 30 days) to a local markdown file.

Uses the same ``DATABASE_URL`` / ``SessionLocal`` pattern as ``scripts/analyze_chat_costs.py``.
Intended for **Railway production** (``railway run ...``). Writes **only** to
``scripts/output/tier3_queries.md`` (UTF-8). No DB writes. Does **not** print query text to stdout.

Unified-router rows store the assistant reply in ``message`` and the (normalized) user query in
``normalized_query``; raw query text is not persisted (see ``query_text_hashed``).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import ChatLog

WINDOW_DAYS = 30
OUT_DIR = _ROOT / "scripts" / "output"
OUT_PATH = OUT_DIR / "tier3_queries.md"


def _fmt_ts(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M")


def _response_preview(text: str | None, limit: int = 200) -> str:
    s = (text or "").replace("\r\n", "\n").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 3] + "..."


def main() -> None:
    cutoff = datetime.now(UTC) - timedelta(days=WINDOW_DAYS)
    extracted_at = datetime.now(UTC).isoformat()

    with SessionLocal() as db:
        stmt = (
            select(ChatLog)
            .where(ChatLog.tier_used == "3", ChatLog.created_at >= cutoff)
            .order_by(ChatLog.created_at.asc())
        )
        rows = list(db.scalars(stmt).all())

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        "# Tier 3 Query Extract — LOCAL REVIEW ONLY",
        "# Contains user query text. Do not commit or share externally.",
        f"# Extracted: {extracted_at}",
        f"# Row count: {len(rows)}",
        "",
        "Unified-router rows: **Query** below is `normalized_query` from the database "
        "(normalized user text). Raw verbatim query is not stored; see `query_text_hashed`.",
        "",
        "---",
        "",
    ]

    for i, r in enumerate(rows, start=1):
        q = r.normalized_query if r.normalized_query is not None else ""
        entity = r.entity_matched if r.entity_matched else "—"
        tokens = r.llm_tokens_used if r.llm_tokens_used is not None else "—"
        lines.extend(
            [
                f"## Row {i}",
                f"- **Timestamp:** {_fmt_ts(r.created_at)}",
                f"- **Query:** {q}",
                f"- **Sub-intent:** {r.sub_intent if r.sub_intent is not None else '—'}",
                f"- **Entity matched:** {entity}",
                f"- **Tokens:** {tokens}",
                f"- **Response (first 200 chars):** {_response_preview(r.message)}",
                "",
            ]
        )

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {len(rows)} Tier 3 row(s) to {OUT_PATH}")


if __name__ == "__main__":
    main()
