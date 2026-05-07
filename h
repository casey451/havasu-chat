[1mdiff --git a/app/chat/entity_matcher.py b/app/chat/entity_matcher.py[m
[1mindex 74de7d3..272425a 100644[m
[1m--- a/app/chat/entity_matcher.py[m
[1m+++ b/app/chat/entity_matcher.py[m
[36m@@ -182,6 +182,44 @@[m [mdef _long_tokens(stripped: str) -> str:[m
     return " ".join(tokens)[m
 [m
 [m
[32m+[m[32m# Voice-battery 2026-05-07: WRatio + partial_token_set_ratio inflate scores when[m
[32m+[m[32m# the query and needle share only one common token (e.g. "havasu" appears in[m
[32m+[m[32m# nearly every Lake Havasu provider name) while the *distinctive* token has no[m
[32m+[m[32m# substring match in the needle. Without a guard, "where can I find havasu lanes"[m
[32m+[m[32m# matches "Altitude Trampoline Park — Lake Havasu City" via the typo path, since[m
[32m+[m[32m# WRatio rewards the shared "havasu" + partial overlap. The graded battery[m
[32m+[m[32m# surfaced six wrong-entity Tier 1 answers from this single failure mode.[m
[32m+[m[32m_TYPO_PER_TOKEN_THRESHOLD = 80.0[m
[32m+[m
[32m+[m
[32m+[m[32mdef _typo_path_passes_guard(long_only: str, needle: str) -> bool:[m
[32m+[m[32m    """``True`` iff every ≥5-char token in ``long_only`` substring-matches ``needle``.[m
[32m+[m
[32m+[m[32m    Uses :func:`fuzz.partial_ratio` (Levenshtein-style best-window ratio) per[m
[32m+[m[32m    query token. If any distinctive query token has no substring-like match in[m
[32m+[m[32m    the needle, the typo scorers (WRatio, partial_token_set_ratio) are not[m
[32m+[m[32m    allowed to fire on this needle — preventing the wrong-entity false positives[m
[32m+[m[32m    surfaced by the voice battery.[m
[32m+[m
[32m+[m[32m    Examples (all use the long-tokens-only stripped form of the query):[m
[32m+[m[32m    - ``"havasu lanes"`` vs ``"havasu lanes"`` → both tokens → PASS.[m
[32m+[m[32m    - ``"havasu lanes"`` vs ``"altitude trampoline park lake havasu city"``:[m
[32m+[m[32m      ``"havasu"`` hits 100, ``"lanes"`` hits ~25 → FAIL (was the bug).[m
[32m+[m[32m    - ``"mudsharks"`` (typo) vs ``"mudshark brewing company"``: ~89 → PASS[m
[32m+[m[32m      (typo tolerance preserved).[m
[32m+[m[32m    - ``"mudshark brewing"`` vs ``"double threat barbering co"``:[m
[32m+[m[32m      ``"mudshark"`` hits ~30, ``"brewing"`` hits ~57 (b/r/i/n shared with[m
[32m+[m[32m      ``barbering``) → FAIL (was the gap-template near-match bug).[m
[32m+[m[32m    """[m
[32m+[m[32m    tokens = [t for t in long_only.split() if len(t) >= 5][m
[32m+[m[32m    if not tokens:[m
[32m+[m[32m        return False[m
[32m+[m[32m    for tok in tokens:[m
[32m+[m[32m        if float(fuzz.partial_ratio(tok, needle)) < _TYPO_PER_TOKEN_THRESHOLD:[m
[32m+[m[32m            return False[m
[32m+[m[32m    return True[m
[32m+[m
[32m+[m
 # Slice F6: Tier-1-shaped intent prefixes that pad a query with stopwords and drag[m
 # token_set_ratio below threshold. Stripping them isolates the entity portion. Examples:[m
 #   "is mudshark open right now"      → "mudshark" (vs "Mudshark Brewing Company" → 90+)[m
[36m@@ -276,6 +314,11 @@[m [mdef _best_score_padded(norm_query: str, needles: frozenset[str]) -> float:[m
             # matches in any longer query string.[m
             if len(needle) < 5:[m
                 continue[m
[32m+[m[32m            # Voice-battery 2026-05-07: per-token substring guard. Without this,[m
[32m+[m[32m            # a single shared common token ("havasu") + WRatio's permissive[m
[32m+[m[32m            # composite scoring lets non-matching needles cross the 75 threshold.[m
[32m+[m[32m            if not _typo_path_passes_guard(long_only, needle):[m
[32m+[m[32m                continue[m
             # Slice F: max of partial_token_set_ratio + WRatio for typo tolerance.[m
             # WRatio combines token_sort + partial_ratio + others with internal[m
             # weighting, which crucially distinguishes "mudsharks brewry" → "mudshark[m
