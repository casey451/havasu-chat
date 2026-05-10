# Backlog #46 — manual production smoke-check queries

**Purpose:** After Railway deploys the entity_matcher #46 fix, paste these queries against the live `/api/chat` endpoint and confirm the responses match the **Expected** column. Cursor's automated test file (`tests/test_entity_matcher_adversarial.py`) covers a subset of these in CI; this doc is the broader manual surface that complements it.

**How to use (PowerShell — `Invoke-RestMethod` avoids the `curl.exe + $body` JSON-mangling bug):**

```powershell
Invoke-RestMethod -Method Post -Uri "https://havasu-chat-production.up.railway.app/api/chat" `
  -ContentType "application/json; charset=utf-8" `
  -Body '{"query":"<paste query here>","session_id":"smoke-46-N"}'
```

> **Why `; charset=utf-8`:** PowerShell's `-Body` defaults to ISO-8859-1 / Windows-1252 when no charset is in `-ContentType`. Accented or non-ASCII characters serialized this way produce invalid UTF-8 bytes that Starlette rejects with HTTP 400 (`{"detail":"There was an error parsing the body"}`) before any app code runs. The `; charset=utf-8` clause forces PowerShell to honor UTF-8 — surfaced by Class E3 (`múdshärk bréwery`); see Backlog #51 close-out.

For the connector-word bypass cases, "Expected: None / no entity match" means the response should **not** name the wrong canonical (e.g. should not say "I think you meant Ross Dress for Less" or auto-dispatch to Number One Nails). A safe gap response or a generic "I'm not sure which business you mean" is correct.

Source: ChatGPT adversarial brainstorm 2026-05-09; voice-battery agent's confirmed cases (2026-05-08); CC's adversarial test file scope.

---

## Class A — Connector-word bypass (the original #46 bug surface)

These queries should NOT match the named canonical. If the response names that canonical (or auto-dispatches to it), the #46 fix is incomplete.

| # | Query | Should NOT match | Bypass mechanism |
|---|---|---|---|
| A1 | `phone for addrss` | Mudshark Brewery and Public House (or Ross Dress for Less) | `address` token via `and` / `for` |
| A2 | `sloane number` | Number One Nails | `sloane` matches `Nails` ≥80 via short token |
| A3 | `mountian biking` | Iron Man Triathlon | `mountain` typo via `and`/`man` |
| A4 | `mudshark address` | altitude trampoline park lake havasu city | `mudshark` partials `lake` |
| A5 | `ironwood` | Iron Man Triathlon | cross-entity via `and`/`man` |
| A6 | `tappp` | random `jiu`/`bmx`-containing needle | bypass via 3-char connectors |
| A7 | `phnepubic addres` | Mudshark Brewery and Public House | `public`/`address` via `and` |
| A8 | `cntrey clib phne` | Iron Wolf Golf and Country Club | `country` typo partial via `and` |
| A9 | `gymnasticcs locatoin` | Universal Gymnastics and All Star Cheer | long typo inflated by `and` |
| A10 | `combat barru schedul` | Bridge City Combat and Barry Sullins Jiu-Jitsu | `schedule` via `jiu` |
| A11 | `taproom instrctor` | The Tap Room Jiu Jitsu | `instructor` via `jiu` |
| A12 | `triathln registartion` | Iron Man Triathlon | `registration` inflated by `man` |
| A13 | `brewry pubic hous numbr` | Mudshark Brewery and Public House | `number` via `and` |
| A14 | `allstar cheer addrss` | Universal Gymnastics and All Star Cheer | `address` via `all` |
| A15 | `jiujitzu coachs` | Bridge City Combat and Barry Sullins Jiu-Jitsu | `coaches` via `jiu` |
| A16 | `thetaprom revws` | The Tap Room Jiu Jitsu | `reviews` via `the` |
| A17 | `cuntryclb membrship` | Iron Wolf Golf and Country Club | `membership` via `and` |
| A18 | `gymnatsic parent potal` | Universal Gymnastics and All Star Cheer | `portal` via `all` |

> **Note:** several A-class cases assume the named canonical exists in the production catalog. If a response says "I don't have a business by that name" for a query whose Expected is "should NOT match X", that's still a pass — it means the matcher correctly returned no match, which is the desired behavior.

## Class B — Cross-needle confusion

These queries could partial-match two different canonicals. Either return the right one or return None — not the wrong one.

| # | Query | Correct match (if any) | Wrong match to avoid |
|---|---|---|---|
| B1 | `mudshark publichous` | Mudshark Brewery and Public House (or None) | any other connector-word needle |
| B2 | `jiujitsu taproom` | The Tap Room Jiu Jitsu (or None) | Bridge City Combat and Barry Sullins Jiu-Jitsu |
| B3 | `barry jitsu class` | Bridge City Combat and Barry Sullins Jiu-Jitsu (or None) | The Tap Room Jiu Jitsu |
| B4 | `ironman golf` | None (the two needles are unrelated entities) | Iron Man Triathlon AND Iron Wolf Golf and Country Club |
| B5 | `allstar gym` | Universal Gymnastics and All Star Cheer | other gym/star canonicals |
| B6 | `tap room combat` | None | arbitrary Jiu-Jitsu result |
| B7 | `brewery country club` | None | Mudshark Brewery OR Iron Wolf Golf |

## Class C — Pathological inputs

These should never produce a match.

| # | Query | Expected |
|---|---|---|
| C1 | (empty string) | None / handled gracefully |
| C2 | `a` | None |
| C3 | `1234567890` | None |
| C4 | `!!!@@@###` | None |
| C5 | `xxxx...` (200 chars of `x`) | None / handled gracefully |

## Class D — Severe-typo NEAR-band preservation (#44 case must still work)

These severe vowel-drop typos should still match in the [55, 75) NEAR band. **Note:** use the realistic `phone for X` chat shape — bare-form typos like `mdshrkbrwry` alone return None due to the existing `_best_score_padded` F6 early-return path (the WRatio scorer only fires when intent-stripping changes the query). Real users always include intent prefixes, so the `phone for` shape is what production sees.

If any return None, the #46 fix went too far and broke the original #44 case.

| # | Query | Should match (NEAR band) |
|---|---|---|
| D1 | `phone for mdshrkbrwry` | Mudshark Brewery and Public House (~65) |
| D2 | `phone for unvrslgymnstcs` | Universal Gymnastics and All Star Cheer |
| D3 | `phone for brdgcitycmbt` | Bridge City Combat and Barry Sullins Jiu-Jitsu |
| D4 | `phone for irnwlfglf` | Iron Wolf Golf and Country Club |
| D5 | `phone for tproomjiujtsu` | The Tap Room Jiu Jitsu |
| D6 | `phone for mudsharks brewry` | Mudshark Brewery and Public House (direct match >75, ~84) |

## Class E — Preprocessing edge cases (separate concerns)

These test pre-matcher normalization, NOT the #46 fix itself. If they fail, file as separate bugs (whitespace stripping, case folding, unicode normalization) — they're orthogonal to the connector-word bypass.

| # | Query | Expected |
|---|---|---|
| E1 | `     mudshark brewery     ` | Match (whitespace-tolerant) |
| E2 | `MUDSHARK BREWERY` | Match (case-tolerant) |
| E3 | `múdshärk bréwery` | Match OR safely None (accent handling) |

> **E3 layer note (post-#51):** the wire-level encoding concern is precondition-met by the `; charset=utf-8` clause documented at lines 9–11 above; this row now exercises only the matcher-side accent-folding behavior, not the Starlette body-parse path.

---

## Pass/fail recording

After running the smoke check, record results as a single line per query in this doc, e.g.:

```
A1 phone for addrss → PASS (response: "I'm not sure which business you mean...")
A2 sloane number → FAIL (response named Number One Nails — bug persists)
```

If any Class A or Class B case FAILS, the #46 fix needs another pass — file Backlog #47 with the failing case and its production response.

If any Class D case FAILS, roll back #46 to its as-shipped state and re-investigate — the fix broke the original #44 severe-typo improvement.
