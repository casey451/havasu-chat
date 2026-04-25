# Review — Tier 3 diagnostics draft (read-only prod + branching plan)

**Context:** Review of a drafted Cursor prompt for read-only prod DB diagnostics via `railway run python`, then Sections A–E (interpretation + branching plan). **No prod commands were run** in producing this file.

---

## Verdict — approve with one **critical** fix to D2

### Fix D2: wrong column for “user said X”

In `log_unified_route` (`app/db/chat_logging.py`), the persisted row uses:

- `message` = **assistant `response_text`** (truncated), not the user’s raw text.

So D2 as written (“user-message column” / searching `message` for `summer` / `july`) will **not** find the validation *queries*. It will search **Hava’s answers**, which may echo themes but won’t line up with “the four validation queries” reliably.

**What to use instead (after D1):**

- Primary filter: **`normalized_query`** (and `ilike` / `%` patterns) — that’s the normalized user query the router logged.
- Optional: also note if **`message`** matches for debugging (assistant echoing “July”), but **tier attribution (D2/D3) should be keyed to rows where `normalized_query` matches**, with `role = 'assistant'` if you join other tables or if mixed roles exist in `chat_logs`.

**Revise the draft** so D1 names columns, then D2 explicitly says:

- *Filter `chat_logs` where `normalized_query` IS NOT NULL and matches the patterns; return `id`, `created_at`, `tier_used`, `mode`, `sub_intent`, `entity_matched`, first 100 chars of `normalized_query` (and optionally first 100 of `message` to see reply shape). Sort `created_at` DESC, limit 15.*

If `normalized_query` is null on older rows, say: *fall back to hashed lookup only for identification, or exclude from “four validation” matching.*

That single change is enough to make D2 + D3 scientifically usable.

---

## `railway run` from Cursor

- **Approve trying it** in Cursor: if the shell has Railway CLI + login + project link, it works the same as locally.
- **If the command errors** (not logged in, no project, network): fallback is **Casey runs the one-liners, pastes output, Cursor only analyzes** — restructure the prompt to “commands appendix + analysis-only for Cursor” when the first `railway run` fails. No need to pre-split unless you know Railway isn’t wired in that environment.

---

## D2 search terms (breadth)

- `summer` and `july` will pull **extra** traffic; for diagnosis that’s **acceptable** if you then **in Section C** pair rows to the *four* validation intents by hand (substring / phrase on `normalized_query`).
- Optional tighten: add patterns like `whats happening`, `4th of july`, `firework`, `july 4` as **separate** filters and tag which bucket each row belongs to. Not required for approval.

---

## D4 title fuzzy match

- Broader is fine for a **discovery** query; you can **interpret** in Section C (e.g. drop rows that are clearly not Independence Day). If you want less noise, add OR title `ilike` `%independence%` and keep july / 4th / firework for recall.

---

## D5 (small precision)

- **Match Option B filters:** `status = 'live'`, `provider_id IS NULL`, `date >= <today>`, `date <= <today> + 365 days` (use **same** notion of “today” as D7 or a single `CURRENT_DATE` in SQL if the DB is in UTC — note any mismatch).
- The question “how many with `date < '2026-07-04'`” is meaningful **within** that unlinked-future set; the draft should say that explicitly so nobody counts past/cancelled rows.

---

## D1 / table name

- `ChatLog` model maps to **`chat_logs`** (`__tablename__ = "chat_logs"` in `app/db/models.py`). Use **`chat_logs`** in SQL, not `ChatLog`.

---

## Summary

| Item | Action |
|------|--------|
| D2 | **Revise** — filter on `normalized_query`; clarify `message` is assistant reply |
| Railway in Cursor | **Approve try**; fallback to Casey-run commands if auth/network fails |
| D2 terms | **OK** as discovery; optional tighter buckets |
| D4 | **OK**; optional `independence` |
| D5 | **Clarify** filters match Option B + “today” |
| D1 | Use table name `chat_logs` |

**Overall:** Revise D2 as above, then **approve** the rest of the draft (ordering D1→D7, Sections A–E, three branches, fences).
