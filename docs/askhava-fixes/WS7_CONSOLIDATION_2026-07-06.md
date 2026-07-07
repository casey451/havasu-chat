# WS7 — Template & component consolidation (verified already complete)

**Date:** 2026-07-06 · **Outcome:** no code change — the consolidation the spec asks for already shipped (mostly the v4.4–v4.6 migration, 2026-07-02..04). Verified against live prod + repo.

| Spec §7 item | Status | Evidence |
|---|---|---|
| One layout shell (header/util/footer) | **Done** | `base_redesign.html` / `base_plain.html` → `lake_redesign.css`; single `_partials/site_header.html` + `_partials/site_footer.html` included by both. The "≥6 header chromes / ≥4 footers" premise is pre-v4.6. |
| M14 raw-label bug (`/chat`, `/account`, day-pager paths as link text) | **Not reproduced** | Live `/categories` + `/events-ui` have zero `>/path<` link labels; nav uses friendly labels ("Today", "Events"), `/chat` is an icon link, the day pager uses ISO-dated friendly nav. |
| M10 canonical taxonomy (one `display_name` everywhere) | **Consistent** | "Eat & Drink", "Places to Stay" (lodging), "Health & Medical" match on `/categories` tiles and each category page H1. |
| M4 counts service (one source, all surfaces) | **Done** | `app/home/redesign.py:directory_launcher` and `/categories` both read `app.categories.router._get_index_payload` (the `_index_cache`) — counts can't diverge by construction. `/categories` shows Eat & Drink 247 from that one source. The spec's 247/254/274 contradiction is pre-dedup/pre-consolidation. |
| One footer + one support email + kill `havasuchat` | **Done** | One `site_footer.html`; the only support email in live templates is `hello@askhava.com` (×8). `havasuchat` survives only in (a) a scraper `USER_AGENT` string and (b) `DEAD_EVENT_LINK_HOSTS` — a blocklist that *names* `havasuchat.com` to strip dead links (correct; must stay). No user-facing use. |

## The one debatable remainder (a product call, not a defect)

**M12 — gas-widget de-duplication.** The util bar renders the cheapest-gas top-5 on every content page (one shared `app.home.redesign.gas_panel_data` source, not divergent code). The spec wants it collapsed to a single header chip that opens `/gas`. That's a UX/product decision (the expander is arguably a feature), it touches the shared shell + its tests (`id="gasPanel"`), and it isn't a correctness bug — so it's flagged for Casey rather than changed here.

**Conclusion:** WS7's substantive migration is complete; no safe code change remains. The "two list-page templates" (old Restaurants vs filtered Colleges) called out under WS7 is really a WS9a concern and is tracked there.
