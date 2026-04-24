# Phase 8.10 hygiene — unrequested commit `3972eec`

Diagnostic record: commit `3972eec` was not part of the scoped orientation-only task; this document captures `git show`, summary, assessment, and remediation options (no execution recorded here).

---

## Step 1 — Full `git show 3972eec` output

```
commit 3972eec2e813ef77577ee3a0b2a2d194cbbd6d14
Author: Casey <caseylsolomon@gmail.com>
Date:   Thu Apr 23 12:27:25 2026 -0700

    fix(8.10): longer read timeout and retries for RiverScene HTML fetches

diff --git a/app/contrib/river_scene.py b/app/contrib/river_scene.py
index b02cf25..69fdf5b 100644
--- a/app/contrib/river_scene.py
+++ b/app/contrib/river_scene.py
@@ -21,7 +21,13 @@ from app.schemas.contribution import ContributionCreate
 SITEMAP_INDEX_URL = "https://riverscenemagazine.com/wp-sitemap.xml"
 EVENTS_SITEMAP_PREFIX = "wp-sitemap-posts-events-"
 USER_AGENT = "Hava/0.1 (+https://github.com/casey451/havasu-chat)"
-REQUEST_TIMEOUT = 10.0
+
+# Sitemaps are small XML; event pages can be slow (WordPress + assets).
+SITEMAP_HTTP_TIMEOUT = httpx.Timeout(45.0, connect=20.0)
+EVENT_PAGE_HTTP_TIMEOUT = httpx.Timeout(120.0, connect=25.0)
+
+# Default ``httpx.Client`` ceiling for :func:`run_pull` (matches event pages).
+REQUEST_TIMEOUT = EVENT_PAGE_HTTP_TIMEOUT
 
 
 @dataclass
@@ -50,26 +56,38 @@ def _sleep_polite() -> None:
     time.sleep(1.0)
 
 
-def _http_get_text(url: str, client: httpx.Client) -> str:
-    """GET ``url`` as text. One retry on timeout or 5xx; then a polite pause."""
+def _http_get_text(
+    url: str,
+    client: httpx.Client,
+    *,
+    timeout: httpx.Timeout | float,
+) -> str:
+    """
+    GET ``url`` as text.
+
+    Retries on connect/read timeout (up to 3 attempts) and once more on 5xx;
+    then a polite pause after a successful response.
+    """
 
     def once() -> httpx.Response:
-        return client.get(url)
+        return client.get(url, timeout=timeout)
 
-    try:
-        r = once()
-        r.raise_for_status()
-    except (httpx.TimeoutException, httpx.ReadTimeout, httpx.ConnectTimeout):
-        time.sleep(0.5)
-        r = once()
-        r.raise_for_status()
-    except httpx.HTTPStatusError as e:
-        if e.response is not None and e.response.status_code >= 500:
-            time.sleep(0.5)
+    r: httpx.Response | None = None
+    for attempt in range(3):
+        try:
             r = once()
             r.raise_for_status()
-        else:
+            break
+        except (httpx.TimeoutException, httpx.ReadTimeout, httpx.ConnectTimeout):
+            if attempt >= 2:
+                raise
+            time.sleep(0.5 + 0.5 * attempt)
+        except httpx.HTTPStatusError as e:
+            if e.response is not None and e.response.status_code >= 500 and attempt < 2:
+                time.sleep(0.5)
+                continue
             raise
+    assert r is not None
     text = r.text
     _sleep_polite()
     return text
@@ -212,13 +230,13 @@ def fetch_sitemap_urls(*, client: httpx.Client | None = None) -> list[str]:
     """
     if client is None:
         with httpx.Client(
-            timeout=REQUEST_TIMEOUT,
+            timeout=SITEMAP_HTTP_TIMEOUT,
             headers=_headers(),
             follow_redirects=True,
         ) as c:
             return fetch_sitemap_urls(client=c)
 
-    xml_index = _http_get_text(SITEMAP_INDEX_URL, client)
+    xml_index = _http_get_text(SITEMAP_INDEX_URL, client, timeout=SITEMAP_HTTP_TIMEOUT)
     root = ET.fromstring(xml_index)
     ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
     sub_locs: list[str] = []
@@ -233,7 +251,7 @@ def fetch_sitemap_urls(*, client: httpx.Client | None = None) -> list[str]:
         if sub in seen_sub:
             continue
         seen_sub.add(sub)
-        xml_page = _http_get_text(sub, client)
+        xml_page = _http_get_text(sub, client, timeout=SITEMAP_HTTP_TIMEOUT)
         subroot = ET.fromstring(xml_page)
         for url_el in subroot.findall("sm:url", ns):
             loc = url_el.find("sm:loc", ns)
@@ -251,14 +269,14 @@ def fetch_and_parse_event(
     """Fetch one event page and parse it. Returns ``None`` if unparseable or start date is in the past."""
     if client is None:
         with httpx.Client(
-            timeout=REQUEST_TIMEOUT,
+            timeout=EVENT_PAGE_HTTP_TIMEOUT,
             headers=_headers(),
             follow_redirects=True,
         ) as c:
             return fetch_and_parse_event(url, client=c, today=today)
 
     as_of = today if today is not None else date.today()
-    html = _http_get_text(url, client)
+    html = _http_get_text(url, client, timeout=EVENT_PAGE_HTTP_TIMEOUT)
     soup = BeautifulSoup(html, "html.parser")
     table = _find_event_details_table(soup)
     if table is None:
```

---

## Step 2 — Summary

1. **Files modified:** `app/contrib/river_scene.py` only.

2. **What changed:** Replaced `REQUEST_TIMEOUT = 10.0` with two `httpx.Timeout` values (sitemap: 45s read / 20s connect; event HTML: 120s read / 25s connect). `REQUEST_TIMEOUT` is set to the event-page timeout. `_http_get_text` now requires `timeout=` and passes it to `client.get`. Retries on timeout/read/connect: up to **three** attempts with backoff; 5xx handling is in the same loop. `fetch_sitemap_urls` and `fetch_and_parse_event` pass the appropriate timeout into `_http_get_text` and into ephemeral clients when `client is None`.

3. **Tests:** No test files were modified in this commit.

4. **Docs / known-issues:** No documentation or `known-issues` updates in this commit.

---

## Step 3 — Assessment

1. **Prompted by a specific user request (orientation-only prompt)?** **No.** In the broader Cursor thread there was a separate report (read timeout on `river_scene_pull --dry-run`) that called for a fix, but that was not a scoped phase prompt with an explicit file list and commit discipline for this commit.

2. **Technically correct?** **Mostly yes** for slow WordPress HTML vs small XML. Minor: docstring wording vs shared 3-attempt loop; timeout and 5xx share one attempt counter.

3. **Could it break existing tests?** **Unlikely** — internal call sites updated; `REQUEST_TIMEOUT` as `httpx.Timeout` remains valid for `httpx.Client(timeout=...)`.

4. **Full suite pass?** **Reasonably expected yes** — no test changes; behavior is more permissive (longer timeouts, more retries).

---

## Step 4 — Remediation options (not executed here)

**Option A — Accept both commits, push as-is**

- Pros: the fix may genuinely improve resilience; minimal disruption
- Cons: normalizes out-of-scope commits; no test coverage added for the new behavior; process rule was broken

**Option B — Revert `3972eec`, keep `80a32f1`, push only the housekeeping commit**

- Execute: `git reset --hard 80a32f1^ && git cherry-pick 80a32f1`
  - (Stated intent: drop `3972eec` entirely, re-apply orientation on top of pre-fix base — verify `80a32f1^` matches the desired base before running; if `80a32f1` sits on top of `3972eec`, this sequence leaves `3972eec` in history unless you reset to `origin/main` first.)
- Then push
- Pros: enforces the process rule cleanly; no ambiguity
- Cons: if the fix is actually useful, we lose it (but it can be re-done as its own properly-scoped phase later)

**Option C — Proper scoped phase**

- Revert locally as in Option B (or equivalent to drop `3972eec` from `main`).
- User drafts Phase 8.10.1 (or similar) with timeout fix **plus** tests and documentation.
- Push orientation first; land the fix through the new prompt.
- Pros: fix + process + coverage
- Cons: more work; delay before fix is on `main`

---

## Step 5 — Status

Remediation was **not** executed as part of writing this file. Choose **A**, **B**, or **C** in chat when ready.
