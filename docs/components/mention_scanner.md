# mention_scanner

`app/contrib/mention_scanner.py` (~117 lines)

## Purpose

Background-task helper that scans a Tier 3 response for title-case local-entity mentions and persists them as `LlmMentionedEntity` rows for later admin review. Drives the **Path 3** catalog-creation flow per `docs/maintainability/end_to_end_creation.md` — Tier 3 mentions a business by name, the scanner notices, the admin reviews and (if appropriate) promotes the mention to a real `Provider` row.

The module is **best-effort and never raises across its boundary.** Failures are logged with full traceback but do not propagate to the request handler that triggered the scan. The unified router fires the scan on a fire-and-forget background task; a scan failure must not corrupt the user's response.

## Public surface

**`MentionCandidate` (dataclass)** — Output of `scan_tier3_response`. Two fields:
- `mentioned_name: str` — the title-case phrase, trailing punctuation trimmed, capped at 300 chars.
- `context_snippet: str` — surrounding text from the response (60 chars on each side; capped at 500 chars total).

**`scan_tier3_response(response_text: str) -> list[MentionCandidate]`** — Pure function, no IO. Extracts unique title-case phrases that aren't on the stop-list. Returns deduplicated within-response candidates.

**`scan_and_save_mentions(chat_log_id, response_text, session_factory) -> None`** — Background-task entry point. Scans the response, opens a DB session via `session_factory()`, persists each candidate via `app.db.llm_mention_store.create_mention`. Wraps everything in `try/except Exception` — best-effort, returns `None` regardless of outcome, logs failures with traceback.

**`STOP_PHRASES` (frozenset)** — Title-case phrases that are NOT local entities even though they look like names: `"Lake Havasu"`, `"Lake Havasu City"`, `"Havasu"`, `"Arizona"`, `"USA"`, weekday names, and others. The scanner skips matches against this set (case-insensitive). Tunable; adding entries is the canonical way to suppress false positives without changing the regex.

## Inputs and outputs

**`scan_tier3_response`:**
- Input: response text (usually Tier 3's assistant string).
- Output: list of `MentionCandidate`. Empty list when no qualifying phrases (every phrase too short, on stop-list, or duplicate within response).

**`scan_and_save_mentions`:**
- Inputs: `chat_log_id` (UUID/string from `chat_logs`), response text, `session_factory` (callable returning a `Session`; usually `SessionLocal`).
- Output: `None`. Side effects: zero or more new `LlmMentionedEntity` rows.

## Internal structure

`scan_tier3_response` is five steps:

1. **URL strip.** `_strip_urls` removes URLs from the text so they don't generate false-positive title-case phrases.
2. **Title-case phrase iteration.** A regex (`_TITLE_PHRASE`) finds title-case spans. The regex is at module top and shouldn't be edited without a focused review — it determines what "looks like a name."
3. **Per-phrase filtering.** For each match:
   - Trim trailing punctuation via `_trim_trailing_punct`.
   - Skip if length < 6 (avoids tiny phrases like "Park" or "Burger").
   - Skip if lower-cased form is in `STOP_PHRASES_LC` (the lower-cased frozenset).
   - Skip if already-seen within this response (within-response dedupe).
4. **Context snippet.** `_context_snippet(cleaned, m.start(), m.end(), radius=60)` returns ±60 characters around the match, capped at 500. The snippet helps the admin reviewer decide whether the mention is a real local entity or a generic reference.
5. **Build `MentionCandidate`.** Cap `mentioned_name` at 300 chars (defensive; the regex shouldn't produce longer matches but the cap protects the DB column constraint).

`scan_and_save_mentions` is three steps:

1. **Open session.** `db = session_factory()`. Wrapped in the outer `try/except`.
2. **Loop + persist.** For each candidate, `create_mention(db, chat_log_id, c.mentioned_name, c.context_snippet)`. The store function handles dedupe-across-mentions if applicable.
3. **Close session in `finally`.** Then any exception propagates to the outer catch, gets logged, and is swallowed.

## Conventions

**Stop-list is lower-cased once at module load.** `STOP_PHRASES_LC = frozenset(s.lower() for s in STOP_PHRASES)` — building it once avoids per-call lowercasing.

**Context snippet capped at 500 chars.** Even if the radius is bumped, the cap prevents a single mention from carrying half the response. Display truncation is admin-UI-side; the cap is a defense against accidental log bloat.

**`mentioned_name` capped at 300 chars.** Matches the `LlmMentionedEntity.mentioned_name` column constraint. Don't lift the cap without coordinated DB migration.

**Length-6 minimum.** Phrases shorter than 6 characters are filtered out. The number is empirical — short phrases generate too many false positives ("Park", "Lake"). Adjust if observed false-positive rates are high in either direction.

**Best-effort persistence.** `scan_and_save_mentions` swallows all exceptions. The unified router calls this on a background task; a scan failure must not propagate to the user-facing response. Logging via `logger.exception` ensures the traceback is preserved for ops review.

**Pure function for the scan, side-effect function for the save.** `scan_tier3_response` is testable without DB; `scan_and_save_mentions` requires a DB fixture. Keep this split when modifying.

## Configuration

No environment configuration. Behavior is driven entirely by:
- The `_TITLE_PHRASE` regex (module top).
- The `STOP_PHRASES` frozenset (module top).
- The `radius` and per-step caps in helper functions.

## Known limitations and design notes

**Title-case heuristic is permissive.** Any title-case phrase ≥ 6 chars not on the stop-list becomes a candidate. False positives are common — "Best Western", "Main Street", "Family Friendly" — and end up in the admin queue for human review. The stop-list is the canonical place to suppress them; growing the stop-list is preferable to tightening the regex.

**No semantic filtering.** The scanner doesn't check whether the phrase is an actual business or just any noun phrase. Tier 3's prompts are voice-shaped to mention real local entities, but the scanner can't tell when the LLM made up a name. Admin review is the safety net.

**Within-response dedupe only.** A response that mentions "Altitude" three times produces one candidate. A subsequent response on a different chat turn that also mentions "Altitude" produces a separate candidate row in `LlmMentionedEntity`. Cross-turn dedupe (or merging) lives in `app/db/llm_mention_store`, not here.

**No URL detection beyond the `_strip_urls` regex.** Inline URLs are removed before scanning, but Markdown links (`[label](url)`) keep the `label` portion. If a Tier 3 response includes `[Altitude](https://example.com)`, "Altitude" gets extracted from the label. Acceptable — the label IS the entity name.

**Background task error logging.** `logger.exception` captures the traceback but the chat log's row doesn't get a "scan failed" indicator. If failures become common, surfacing them in the admin queue would be valuable.

**Stop-list is not extensible at runtime.** Hard-coded frozenset. Adding stop phrases requires a code change. If the stop-list becomes unwieldy, moving it to a DB table or config file would let admins curate it.

## Related

**Direct callers:**

- `app/chat/unified_router.py` — calls `scan_and_save_mentions` as a background task after Tier 3 answers. Passes `chat_log_id`, the response text, and the session factory. Fire-and-forget; the route handler doesn't await.

**Direct dependencies:**

- `app/db/llm_mention_store.create_mention` — actual persistence. The scanner stays pure-Python plus the persistence call; coupling is one function.
- `sqlalchemy.orm.Session` — type annotation for the session factory output.

**Cross-references:**

- `docs/maintainability/end_to_end_creation.md` Path 3 — this module's role in catalog creation.
- `docs/components/river_scene.md` — Path 1+2 (RS-only ingestion).
- `docs/components/approval_service.md` — the materialization layer that promotes mentions to catalog rows.
- `app/admin/mentions_html.py` — admin UI for the mention review queue.
- `app/api/routes/admin_mentions.py` — JSON API for mention promotion.
