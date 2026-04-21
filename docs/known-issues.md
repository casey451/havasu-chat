Known issues tracker: one-line log for bugs deferred in favor of higher-priority work.

### Tier 3 feedback thumbs not rendering (Phase 6.2.2)

**Status:** Deferred. Backend fully functional; frontend render bug.

**Discovered:** 2026-04-21, during Phase 6.2.2 post-ship manual smoke on mobile (incognito, production). Expected thumbs under Tier 3 assistant responses; none rendered.

**Scope:** Frontend only. `POST /api/chat/feedback` endpoint works (Phase 6.2.1 smoke passed, OpenAPI lists route). No data loss — feedback column remains nullable until the UI is fixed.

**Ruled out via diagnostic:**
- Wire format mismatch: API returns `tier_used: "3"` (string) and valid `chat_log_id` (UUID string) — matches frontend's strict `=== "3"` gate.
- Stale cache: reproduced in incognito on a fresh session.
- Served HTML divergence: production `/` matches `app/static/index.html` at HEAD byte-for-byte (after LF/CRLF normalization).
- Schema type: `ConciergeChatResponse.tier_used` typed as `str` in `app/schemas/chat.py`.
- `addRow` signature: returns `{row, bubble}` as expected.
- `pendingRow` scope: closed over and available at thumb-attach call site.
- `attachFeedbackThumbs` early-return: only triggers on missing `chatLogId` or pre-existing `.msg-feedback` child.

**Not yet tested:**
- Browser DevTools Console during Tier 3 render — any runtime errors after `pendingBubble.textContent` assignment?
- Response body as seen by the browser vs. what curl captured (network-tab Response tab capture).
- Browser extension interference on owner's mobile Chrome.
- Mobile viewport-specific CSS bug (thumbs rendering but invisible off-screen or zero-height).

**Fix path when resumed:**
1. Desktop Chrome + DevTools Console + Network tab, incognito.
2. Send a clear Tier 3 query ("whats fun for kids this weekend").
3. Capture Console errors (red/yellow) and Network -> /api/chat -> Response tab verbatim.
4. If Console is clean and response matches curl, build a minimal harness (see Round 2 investigation doc, Part F) to isolate whether the thumb logic itself or integration with the submit path is broken.

**Investigation docs (preserved):**
- `docs/phase-6-2-2-tier3-thumbs-diagnosis-622.md` — Round 1 (wire format).
- `docs/phase-6-2-2-tier3-thumbs-round2-report.md` — Round 2 (HTML parity + handler + schema + harness plan).
- `docs/phase-6-2-2-tier3-thumbs-investigation.md` — consolidated.

**Blocks:** Real feedback data collection until fixed. Does not block Phase 6.2.3 (admin analytics view) — the view will correctly surface the empty state and activate when data starts flowing.

**Priority:** Must fix before soft launch. Not urgent before then.
