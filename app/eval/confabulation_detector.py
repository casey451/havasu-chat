"""Confabulation detector: Layers 1–3. Lexicons: ``relay/halt1-closure-final-lexicons.md``.

POS tagging uses default Penn tags from ``nltk.pos_tag``.

**Layer 1 (``1_advisory``):** per-row scoped lemma diff — **advisory** (candidate tokens for
human review; does not gate the headline confabulation rate; see spec §3.5.1 / §3.6).

**Layer 2 / 3 (``2``, ``3``):** **gating** — headline rates and per-row gating stats use
these layers only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final, Literal

# Layer 2 closure list (AV removed; keep A/V).
_L2: Final[str] = (
    "heated, unheated, indoor, outdoor, private, semi-private, air-conditioned, air conditioned, "
    "climate-controlled, climate controlled, covered, shade, shaded, full sun, pool, poolside, patio, "
    "deck, bar, bar seating, bar area, sound system, A/V, green room, studio, black box, walk-in, "
    "locker room, splash pad, wading, shallow end, deep end, lap lane, heat, "
    "family-friendly, family friendly, kid-friendly, kid friendly, kid-appropriate, kid appropriate, "
    "all-ages, all ages, romantic, date-night, date night, upscale, casual, cozy, intimate, quiet, lively, "
    "perfect for, ideal for, beginner-friendly, teen-friendly, adults-only, adult-only, 18+, 21+, "
    "book online, book through, book on, book directly, call ahead, walk-ins welcome, walk in, no reservation, "
    "reservations required, RSVP, tickets, cover charge, door, at the door, waitlist, spoilers, sign up, "
    "preregister, preregistration, first-come, first served, day-of, drop-in, enrollment, paperwork, "
    "liability, waiver"
)
LAYER2: Final[tuple[str, ...]] = tuple(
    sorted({_p.strip() for _p in _L2.split(",") if _p.strip()}, key=lambda x: (-len(x), x))
)

# HALT 1 + HALT G1 safe framing expansion (generic scaffolding words only).
SAFE: Final[frozenset[str]] = frozenset(
    """
    worth check try head swing pop stop grab start look
    nice decent good great solid fun main
    place spot venue option options kind area part town scene
    usually often sometimes might may likely probably around about
    landscape mix bridge channel mcculloch sara park desert
    offer detail current specific instruction outfit way first reach phone number list directory
    address contact info information available listed small big near close directly currently also
    just still only locate listing context details general generally local nearby
    happen extra full hour pricing call lap
    """.split()
)

VGEN: Final[frozenset[str]] = frozenset(
    "be am is are was were been being have has had do does did can could should would will shall may must might "
    "get go got going went gone make made take came come let know see use used look need find give keep put ask "
    "want try seem feel say tell work call help show mean become include continue set learn lead "
    "understand watch follow start stop read run move live believe hold bring write sit stand lose pay meet play "
    "seem like include".split()
)

QTY: Final[tuple[str, ...]] = (
    "a couple",
    "couple of",
    "a few",
    "several",
    "multiple",
    "dozen",
    "dozens",
    "handful",
    "few",
    "many",
    "most",
    "numerous",
    "various",
    "some",
    "majority",
    "minority",
    "couple",
)

CONTRACTIONS: Final[frozenset[str]] = frozenset({"'re", "'m", "'s", "'ve", "'d", "'ll", "n't"})
LEMMA_CANON: Final[dict[str, str]] = {"outdoors": "outdoor", "indoors": "indoor"}

# Strip before Layer 1 / evidence lemmas so POS asymmetry (CD vs NN) cannot flag phones in L1.
# Order: parenthesized area code + exchange + subscriber **before** bare ``ddd-dddd`` so
# ``(602) 555-1212`` is not split into a spurious ``555-1212`` local match.
# NANP-style numbers; Layer 3 ``ph:`` tokens still canonicalize digits for invented-number diffs.
_PHONE_RE: Final[re.Pattern[str]] = re.compile(
    # ``(602) 555-1212`` — avoid a leading ``\b`` before ``(`` (no word boundary after space).
    r"(?<![0-9])\(\s*\d{3}\s*\)\s*\d{3}[-.\s]?\d{4}\b"
    r"|\b(?:\+?1[-.\s]?)?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"
    r"|\b\d{3}[-.\s]?\d{4}\b"
)


def _strip_phone_numbers(s: str) -> str:
    return _PHONE_RE.sub(" ", s or "")


def _nanp_phone_key(match_or_digits: str) -> str | None:
    raw = re.sub(r"\D", "", match_or_digits)
    if len(raw) == 11 and raw.startswith("1"):
        raw = raw[1:]
    if len(raw) == 10:
        return raw
    if len(raw) == 7:
        return raw
    return None


@dataclass(frozen=True, slots=True)
class DetectorHit:
    # ``1_advisory`` = L1 (advisory); ``2`` / ``3`` = gating.
    layer: Literal["1_advisory", "2", "3"]
    token: str
    sentence_index: int
    row_ids_in_scope: tuple[str, ...]


@dataclass
class InvocationResult:
    response_text: str
    evidence_row_dicts: list[dict[str, Any]]
    http_degraded: bool = False
    is_http_mode: bool = False


_wnl: Any = None


def _prep_text(s: str) -> str:
    # Fix em/en dash token gluing.
    return (s or "").replace("—", " ").replace("–", " ")


def _nltk() -> None:
    global _wnl
    if _wnl is not None:
        return
    import nltk

    for p in (
        "wordnet",
        "omw-1.4",
        "punkt",
        "averaged_perceptron_tagger_eng",
        "punkt_tab",
        "stopwords",
    ):
        nltk.download(p, quiet=True)
    from nltk.stem import WordNetLemmatizer

    _wnl = WordNetLemmatizer()


def _wpos(t: str) -> str:
    from nltk.corpus import wordnet as wn

    if t.startswith("J"):
        return wn.ADJ
    if t.startswith("V") or t == "MD":
        return wn.VERB
    if t.startswith("N"):
        return wn.NOUN
    if t.startswith("R"):
        return wn.ADV
    return wn.NOUN


def _norm_lemma(x: str) -> str:
    return LEMMA_CANON.get(x, x)


def _row_text(d: dict[str, Any]) -> str:
    p: list[str] = []
    for k in (
        "name",
        "description",
        "address",
        "phone",
        "hours",
        "website",
        "cost",
        "location",
        "location_name",
        "category",
        "activity_category",
        "provider_name",
        "age_range",
    ):
        v = d.get(k)
        if v and not isinstance(v, (list, dict)):
            p.append(str(v))
    for k in ("date", "start_time", "end_time"):
        if d.get(k) is not None:
            p.append(str(d[k]))
    for k in ("tags", "schedule_days"):
        v = d.get(k)
        if isinstance(v, (list, tuple, set)):
            for x in v or ():
                p.append(str(x))
    if d.get("schedule_hours"):
        p.append(str(d["schedule_hours"]))
    return _prep_text(" ".join(p))


def _row_id(d: dict[str, Any]) -> str:
    t, n = str(d.get("type", "")), str(d.get("name", ""))
    if t == "event" and d.get("date"):
        return f"{t}:{n}:{d['date']}"
    return f"{t}:{n}"


def _sents(s: str) -> list[str]:
    txt = _prep_text(s)
    if not txt.strip():
        return []
    x = re.split(r"(?<=[.!?])\s+", txt.strip())
    return [a for a in x if a] or [txt.strip()]


def _lemmas(text: str) -> set[str]:
    _nltk()
    from nltk import pos_tag, word_tokenize
    from nltk.corpus import stopwords

    wnl = _wnl
    st = set(stopwords.words("english"))
    out: set[str] = set()
    allow = {
        "NN",
        "NNS",
        "JJ",
        "JJR",
        "JJS",
        "RB",
        "RBR",
        "RBS",
        "VBG",
        "VBD",
        "VBN",
        "VBP",
        "VBZ",
        "VB",
    }
    blob = _strip_phone_numbers(_prep_text((text or "").lower()))
    for w, tag in pos_tag(word_tokenize(blob)):
        if w in ("``", "''", "'s", "'") or w in CONTRACTIONS:
            continue
        if not re.search(r"[a-z-]", w):
            continue
        if tag in ("$", "CD") or w.isdigit():
            continue
        if tag not in allow:
            continue
        lem = _norm_lemma(wnl.lemmatize(w, _wpos(tag)).lower())  # type: ignore[union-attr]
        if w in st or lem in st:
            continue
        if tag[0] == "V" and (lem in VGEN or w in VGEN):
            continue
        if lem in SAFE or w in SAFE:
            continue
        out.add(lem)
    # POS-tagging can miss adjective/adverb outdoor|outdoors forms; normalize explicitly.
    txt = _prep_text((text or "").lower())
    if re.search(r"\boutdoors?\b", txt):
        out.add("outdoor")
    if re.search(r"\bindoors?\b", txt):
        out.add("indoor")
    return out


def _l1(response: str, ev: set[str], rids: tuple[str, ...]) -> list[DetectorHit]:
    _nltk()
    from nltk import pos_tag, word_tokenize
    from nltk.corpus import stopwords

    wnl = _wnl
    st = set(stopwords.words("english"))
    allow = {
        "NN",
        "NNS",
        "JJ",
        "JJR",
        "JJS",
        "RB",
        "RBR",
        "RBS",
        "VBG",
        "VBD",
        "VBN",
        "VBP",
        "VBZ",
        "VB",
    }
    hits: list[DetectorHit] = []
    seen: set[str] = set()
    for si, sent in enumerate(_sents(response)):
        sent_masked = _strip_phone_numbers(_prep_text(sent.lower()))
        for w, tag in pos_tag(word_tokenize(sent_masked)):
            if w in ("``", "''", "'s", "'") or w in CONTRACTIONS or not re.search(r"[a-z-]", w):
                continue
            if tag in ("$", "CD") or w.isdigit() or tag not in allow:
                continue
            lem = _norm_lemma(wnl.lemmatize(w, _wpos(tag)).lower())  # type: ignore[union-attr]
            if w in st or lem in st:
                continue
            if tag[0] == "V" and (lem in VGEN or w in VGEN):
                continue
            if lem in SAFE or w in SAFE:
                continue
            if lem in ev or lem in seen:
                continue
            seen.add(lem)
            hits.append(DetectorHit("1_advisory", lem, si, rids))
    return hits


def _l2_phrase_in(phrase: str, text: str) -> bool:
    pl, txt = phrase.lower(), (text or "")
    if " " in pl or "/" in phrase or phrase in ("A/V", "18+", "21+") or "-" in phrase or re.search(r"^\d", phrase):
        return pl in txt.lower()
    return re.search(r"(?i)(?<![a-z0-9+])" + re.escape(phrase) + r"(?![a-z0-9+])", txt) is not None


def _l2(r: str, e: str, rids: tuple[str, ...], degraded: bool) -> list[DetectorHit]:
    hits: list[DetectorHit] = []
    sents = _sents(r)
    for ph in LAYER2:
        if not _l2_phrase_in(ph, r):
            continue
        if not degraded and _l2_phrase_in(ph, e):
            continue
        si = 0
        for j, s in enumerate(sents):
            if _l2_phrase_in(ph, s):
                si = j
                break
        hits.append(DetectorHit("2", ph, si, rids))
    return hits


def _l3_time_canon(h: int, m: int) -> str | None:
    if 0 <= h <= 23 and 0 <= m <= 59:
        return f"t:{h:02d}:{m:02d}"
    return None


def _l3_add_time_tokens(t: set[str], u: str) -> None:
    """Collect symmetric ``t:HH:MM`` tokens (spec §3.5.3): ranges, 12h+am/pm, then 24h (two-digit hour)."""
    for m in re.finditer(
        r"\b([01]?\d|2[0-3]):([0-5]\d)\s*[-–—]\s*([01]?\d|2[0-3]):([0-5]\d)\b",
        u,
    ):
        for idx in (0, 1):
            h, mi = int(m.group(1 + 2 * idx)), int(m.group(2 + 2 * idx))
            tok = _l3_time_canon(h, mi)
            if tok:
                t.add(tok)
    l12 = list(
        re.finditer(
            r"(?i)\b(1[0-2]|[0-9]):([0-5]\d)\s*([ap])\.?m\.?",
            u,
        )
    )
    u24 = u
    for m in reversed(l12):
        h12, mi, ap0 = int(m.group(1)), int(m.group(2)), m.group(3).lower()
        is_pm = ap0 == "p"
        is_am = not is_pm
        if h12 == 12:
            h24 = 0 if is_am else 12
        else:
            h24 = h12 if is_am else h12 + 12
        tok = _l3_time_canon(h24, mi)
        if tok:
            t.add(tok)
        n = m.end() - m.start()
        u24 = u24[: m.start()] + (" " * n) + u24[m.end() :]
    for m in re.finditer(r"\b(0[0-9]|1[0-9]|2[0-3]):([0-5]\d)\b", u24):
        h, mi = int(m.group(1)), int(m.group(2))
        tok = _l3_time_canon(h, mi)
        if tok:
            t.add(tok)


def _l3_tokens(blob: str) -> set[str]:
    raw = blob or ""
    # Preserve time ranges before :func:`_prep_text` turns en/em dashes into spaces.
    raw = re.sub(
        r"(\d{1,2}:\d{2})\s*[\u2013\u2014]\s*(\d{1,2}:\d{2})",
        r"\1-\2",
        raw,
    )
    t: set[str] = set()
    u = _prep_text((raw or "").lower())
    if re.search(r"\b(free|no charge|no cost)\b", u) or re.search(r"\$0(?:\.00)?\b", u):
        t.add("c:free")
    for m in re.finditer(r"under\s+\$?\s*(\d+)", u):
        t.add(f"lte:{m.group(1)}")
    for m in re.finditer(r"(\$?\d+)\s*(to|[-–—])\s*(\$?\d+)(?:\s+dollars?)?", u, re.IGNORECASE):
        if "$" not in m.group(0):
            continue
        t.add(f"r:{m.group(1).lstrip('$')}-{m.group(3).lstrip('$')}")
    for m in re.finditer(r"\$\s*(\d+)(?:\.(\d{2}))?\b", u):
        d = int(m.group(1))
        cents = m.group(2)
        if d == 0 and (cents is None or cents == "00"):
            continue
        if cents is None or cents == "00":
            t.add(f"usd:{d}")
        else:
            t.add(f"usd:{d}.{cents}")
    for m in _PHONE_RE.finditer(u):
        pk = _nanp_phone_key(m.group(0))
        if pk:
            t.add("ph:" + pk)
    _l3_add_time_tokens(t, u)
    for _ in re.finditer(r"90[- ]?minute|90\s*min(utes?)?|90 min", u, re.IGNORECASE):
        t.add("dur:90m")
    for _ in re.finditer(r"(\b1\b|one)\s*[-]?(h|hr|hour|hours)\b", u, re.IGNORECASE):
        t.add("dur:60m")
    for w in "mon tue tues wed thu thur thurs fri sat sun monday tuesday wednesday thursday friday saturday sunday".split():
        if re.search(rf"\b{w}\.?\b", u, re.IGNORECASE):
            t.add(f"dy:{w[:3].lower()}")
    for s in QTY:
        if re.search(r"(?:" + re.escape(s).replace(" ", r"\s+") + r")", u, re.IGNORECASE):
            t.add(f"qt:{s.replace(' ', '_')}")
    return t


def detect(inv: InvocationResult) -> list[DetectorHit]:
    rows = inv.evidence_row_dicts
    resp = _prep_text(inv.response_text or "")
    eb = " ".join(_row_text(x) for x in rows) if rows else ""
    rids = tuple(_row_id(x) for x in rows) if rows else tuple()
    out: list[DetectorHit] = []
    web = inv.is_http_mode or inv.http_degraded
    if rows and not web:
        out.extend(_l1(resp, _lemmas(eb), rids))
    out.extend(_l2(resp, eb, rids, degraded=not bool(rows) or web))
    if rows:
        for tok in sorted(_l3_tokens(resp) - _l3_tokens(eb)):
            out.append(DetectorHit("3", tok, 0, rids))
    return out
