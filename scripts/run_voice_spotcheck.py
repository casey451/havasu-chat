"""Phase 4.4 — voice spot-check battery against production /api/chat + chat_logs correlation.

Diagnostic only — not imported by app. Uses stdlib HTTP + optional ``railway run`` for DB rows.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib import error, request

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

PRODUCTION_BASE = "https://havasu-chat-production.up.railway.app"
QUERIES: list[str] = [
    "What should I do Saturday?",
    "Pick one thing to do with kids this weekend",
    "What's the best BMX program in town?",
    "Is the farmers market worth it?",
    "Your favorite event coming up?",
    "Things to do this weekend",
    "Family activities this month",
    "Kids programs at Rotary Park",
    "Events tomorrow",
    "Stuff happening at Sara Park",
    "Does Rotary Park have programs for 8-year-olds?",
    "When does the farmers market start on Thursday?",
    "What's at the skate park?",
    "Is Altitude open late on Friday?",
    "When's the next BMX race?",
    "Where's the best sushi in town?",
    "Boat rentals on the lake?",
    "Weather this weekend?",
    "Any good hiking trails?",
    "Is there live music tonight?",
]


def _venv_python() -> Path:
    if sys.platform == "win32":
        return _ROOT / ".venv" / "Scripts" / "python.exe"
    return _ROOT / ".venv" / "bin" / "python"


def post_api_chat(base: str, query: str, session_id: str, timeout: float = 90.0) -> dict:
    payload = json.dumps({"query": query, "session_id": session_id}).encode("utf-8")
    req = request.Request(
        f"{base.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.monotonic()
    try:
        with request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8")
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {"_raw": body}
            return {"ok": True, "status": r.status, "body": parsed, "latency_ms": elapsed_ms}
    except error.HTTPError as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return {
            "ok": False,
            "status": e.code,
            "body": e.read().decode("utf-8", "replace"),
            "latency_ms": elapsed_ms,
        }
    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return {"ok": False, "status": None, "body": str(e), "latency_ms": elapsed_ms}


def cmd_dump_db_rows(session_id: str) -> None:
    from sqlalchemy import select

    from app.db.database import SessionLocal
    from app.db.models import ChatLog

    with SessionLocal() as db:
        q = (
            select(ChatLog)
            .where(ChatLog.session_id == session_id[:128])
            .order_by(ChatLog.created_at.asc())
        )
        rows = db.scalars(q).all()
    out = [
        {
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "normalized_query": r.normalized_query,
            "tier_used": r.tier_used,
            "llm_input_tokens": r.llm_input_tokens,
            "llm_output_tokens": r.llm_output_tokens,
            "latency_ms": r.latency_ms,
        }
        for r in rows
    ]
    print(json.dumps(out))


def fetch_db_rows_via_railway(session_id: str) -> tuple[list[dict] | None, str | None]:
    railway_exe = shutil.which("railway")
    if not railway_exe:
        return None, "railway CLI not found on PATH"
    py = _venv_python()
    if not py.is_file():
        return None, f"venv python not found at {py}"
    script = Path(__file__).resolve()
    cmd = [railway_exe, "run", str(py), str(script), "--dump-db-rows", session_id]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return None, "railway CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return None, "railway run timed out"
    if proc.returncode != 0:
        err = (proc.stderr or "") + (proc.stdout or "")
        return None, f"railway run exit {proc.returncode}: {err.strip()}"
    text = (proc.stdout or "").strip()
    if not text:
        return None, "empty stdout from railway db dump"
    try:
        return json.loads(text), None
    except json.JSONDecodeError as e:
        return None, f"invalid JSON from db dump: {e}: {text[:500]}"


def run_smoke(base: str) -> tuple[bool, str]:
    sid = f"voice-smoke-{uuid.uuid4().hex[:12]}"
    r = post_api_chat(base, "what should I do Saturday", sid)
    if not r.get("ok"):
        return False, f"HTTP {r.get('status')}: {r.get('body')!r}"
    body = r.get("body")
    if not isinstance(body, dict):
        return False, f"unexpected body type: {type(body)}"
    resp = (body.get("response") or "").strip()
    if not resp:
        return False, "empty response field"
    return True, "ok"


def run_battery(base: str, pause_s: float = 1.5) -> tuple[str, list[dict], list[dict] | None, str | None]:
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%MZ")
    stamp_fs = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M")
    sid = f"voice-spot-{stamp_fs}-{uuid.uuid4().hex[:10]}"
    results: list[dict] = []
    for i, q in enumerate(QUERIES, start=1):
        r = post_api_chat(base, q, sid)
        if r.get("ok") and isinstance(r.get("body"), dict):
            body = r["body"]
            text = body.get("response", "")
            tier_http = body.get("tier_used")
            lat_http = body.get("latency_ms", r.get("latency_ms"))
        else:
            text = f"HTTP ERROR {r.get('status')}: {r.get('body')}"
            tier_http = None
            lat_http = r.get("latency_ms")
        results.append(
            {
                "index": i,
                "query": q,
                "http": r,
                "response_preview": text[:12000],
                "tier_http": tier_http,
                "latency_ms_http": lat_http,
            }
        )
        if i < len(QUERIES):
            time.sleep(pause_s)

    db_rows, db_err = fetch_db_rows_via_railway(sid)
    return sid, results, db_rows, db_err


def _md_escape_fence(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def write_report(
    path: Path,
    base: str,
    sid: str,
    results: list[dict],
    db_rows: list[dict] | None,
    db_err: str | None,
    iso_header: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        f"# Voice Spot-Check — {iso_header}",
        f"# Production URL: {base}",
        "# Battery: 20 queries (Phase 3 voice battery)",
        "",
    ]
    if db_err:
        lines.append(f"**WARNING — chat_logs correlation:** {db_err}")
        lines.append("")
    elif db_rows is not None and len(db_rows) != len(QUERIES):
        lines.append(
            f"**WARNING — row count mismatch:** expected {len(QUERIES)} chat_logs rows, got {len(db_rows)} "
            f"(session_id `{sid}`)."
        )
        lines.append("")
    lines.append(f"**session_id:** `{sid}`")
    lines.append("")
    lines.append("---")
    lines.append("")

    for rec in results:
        i = rec["index"]
        q = rec["query"]
        text = rec["response_preview"]
        lat = rec.get("latency_ms_http")
        tier_meta: str | None = None
        tin: object | None = None
        tout: object | None = None
        lat_db: object | None = None
        if db_rows is not None and len(db_rows) == len(QUERIES):
            row = db_rows[i - 1]
            tier_meta = row.get("tier_used")
            tin = row.get("llm_input_tokens")
            tout = row.get("llm_output_tokens")
            lat_db = row.get("latency_ms")
        elif db_rows is not None and i - 1 < len(db_rows):
            row = db_rows[i - 1]
            tier_meta = row.get("tier_used")
            tin = row.get("llm_input_tokens")
            tout = row.get("llm_output_tokens")
            lat_db = row.get("latency_ms")
            if i == 1:
                lines.append(
                    "*Note: DB row count does not match 20 queries; metadata mapped by index may be misaligned.*"
                )
                lines.append("")
        else:
            tier_meta = rec.get("tier_http")

        lines.append(f"## Query {i}")
        lines.append(f"- **Query:** {q}")
        lines.append(f"- **tier_used:** {tier_meta if tier_meta is not None else '(unavailable)'}")
        lines.append(f"- **llm_input_tokens:** {tin if tin is not None else '(unavailable)'}")
        lines.append(f"- **llm_output_tokens:** {tout if tout is not None else '(unavailable)'}")
        if lat is not None:
            lines.append(f"- **Latency (ms):** {lat} (client HTTP elapsed)")
        if lat_db is not None:
            lines.append(f"- **Latency server logged (ms):** {lat_db}")
        lines.append("- **Response:**")
        lines.append("")
        lines.append(_md_escape_fence(text))
        lines.append("")
        lines.append("---")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Voice spot-check battery (Phase 4.4)")
    ap.add_argument(
        "--dump-db-rows",
        metavar="SESSION_ID",
        help="internal: print chat_logs JSON for session (use with railway run + DATABASE_URL)",
    )
    ap.add_argument(
        "--base",
        default=PRODUCTION_BASE,
        help="API base URL (default: production)",
    )
    ap.add_argument(
        "--skip-smoke",
        action="store_true",
        help="skip pre-battery smoke POST (not recommended)",
    )
    args = ap.parse_args()
    if args.dump_db_rows:
        cmd_dump_db_rows(args.dump_db_rows)
        return 0

    base = args.base.rstrip("/")
    if not args.skip_smoke:
        ok, msg = run_smoke(base)
        if not ok:
            print("Smoke test failed — production may be down or request shape rejected.", file=sys.stderr)
            print(msg, file=sys.stderr)
            print(
                "Note: concierge expects JSON {\"query\": \"...\", \"session_id\": \"...\"} on POST /api/chat.",
                file=sys.stderr,
            )
            return 1
        print("Smoke test: OK")

    iso_header = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp_fs = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M")
    out_path = _ROOT / "scripts" / "output" / f"voice_spotcheck_{stamp_fs}.md"

    sid, results, db_rows, db_err = run_battery(base)
    write_report(out_path, base, sid, results, db_rows, db_err, iso_header)
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
