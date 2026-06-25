"""Generic vision-LLM calendar/flyer extractor (build-only, dry-run).

Reads an activities-calendar grid or an event flyer IMAGE into structured event
rows via a vision-capable OpenAI model. Built **generic** -- image bytes + a
prompt variant + a tag set in, validated rows out -- so the Parks & Rec monthly
calendar, the Parks & Rec event flyers, and (later) the senior-center flyers are
thin adapters over ONE engine rather than three copies.

This exists because Lake Havasu City Parks & Recreation (and the senior center)
publish program content as IMAGES -- a monthly calendar flyer and individual
event flyers -- that carry free/drop-in/special events appearing nowhere else in
machine-readable form. Our text/feed scrapers physically cannot see them. The
hand-maintained ``app.events.senior_center.CURATED_SPECIAL_EVENTS`` table is the
manual answer today; this is the engine that replaces manual transcription.

The two failure modes of LLM transcription, and the guardrails (build brief §6):

  * month-bounding   -- a row whose date falls outside the calendar's own
                        title-derived month/year is DROPPED (the model invented
                        a date for a different month).
  * provenance       -- every kept row must echo the verbatim cell text it read
                        (``source_cell``); a row that cannot show its work is
                        DROPPED (the model fabricated an event).
  * confidence gate  -- a row below :data:`CONFIDENCE_THRESHOLD` is HELD (hidden,
                        pending_review) rather than dropped, so a vision guess
                        never lands live without a human glance.
  * self-check       -- :func:`apply_self_check_flags` demotes any date the model
                        flags as unsure on a cheap second pass to held.

No DB access here, no orchestrator wiring. Degrades to ``[]`` (one log line) when
``OPENAI_API_KEY`` is absent -- mirrors :mod:`app.core.extraction`. Parsing and
validation are pure so the test suite exercises every guard with recorded model
JSON and never makes a live LLM / HTTP call.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, time, timedelta

try:  # same guarded-import pattern as the other OpenAI call sites
    from openai import OpenAI
except ImportError:  # pragma: no cover -- openai always present in prod
    OpenAI = None  # type: ignore[misc, assignment]

from app.core.llm_http import LLM_CLIENT_READ_TIMEOUT_SEC
from app.core.openai_client import get_openai_client

logger = logging.getLogger(__name__)

# A row below this confidence is written HIDDEN (draft + pending_review), never
# live -- vision rows must earn their way onto the calendar (build brief §5/§6).
CONFIDENCE_THRESHOLD = 0.75
DEFAULT_VISION_MODEL = "gpt-4o"
# A real event title is a short label, never a paragraph. Anything longer is the
# model leaking the cell body into the title field and is dropped.
TITLE_MAX_LEN = 120

# A dense monthly calendar image consumes most of a small model's context window,
# leaving too few tokens to emit the full ~30-event JSON -> the reply is truncated
# -> unparseable -> 0 events (diagnosed on the CPU-only VPS, 2026-06-24). Give the
# call a bigger context + output budget. ``VISION_MAX_TOKENS`` caps the reply and is
# a first-class OpenAI param, honored on every backend.
#
# ``VISION_NUM_CTX`` is sent via ``extra_body={"options": {...}}`` on the self-hosted
# path only (real OpenAI rejects the unknown field). CAVEAT (VPS, 2026-06-24): Ollama's
# OpenAI-compatible ``/v1/chat/completions`` endpoint IGNORES this -- the model stays
# pinned at its built-in context (4096) regardless. Some OpenAI-compatible servers
# (vLLM) do honor it, so it is kept, but for Ollama you must bake the window into the
# model (Modelfile ``PARAMETER num_ctx``; see deploy/vps-vision/havasu-qwen-cal.Modelfile)
# OR -- better on a CPU box -- split the grid into tiles (below) so each request's
# image + output is small enough to fit the default window.
VISION_NUM_CTX = int(os.getenv("VISION_NUM_CTX", "8192"))
VISION_MAX_TOKENS = int(os.getenv("VISION_MAX_TOKENS", "4096"))

# Tiling: a dense recurring-heavy month overflows even a raised budget (the full
# event list is just too long for a small CPU model to emit in one reply). Splitting
# the calendar image into N overlapping horizontal bands keeps each request's image
# AND its output small, so it fits the default window and stays fast per call; the
# rows are merged + deduped across tiles. Default 1 (off) so OpenAI / non-dense use is
# unchanged; the self-hosted VPS sets VISION_CALENDAR_TILES=2 (or 3).
VISION_CALENDAR_TILES = int(os.getenv("VISION_CALENDAR_TILES", "1"))
VISION_CALENDAR_TILE_OVERLAP = float(os.getenv("VISION_CALENDAR_TILE_OVERLAP", "0.12"))

# Image safety (2026-06-25): the gallery sometimes serves a documentID that is NOT
# a raster image (an HTML error page, a PDF, an empty/zero-byte body, or the wrong
# content-type). Base64-ing that into an ``image_url`` part makes the vision API
# reject the whole call with a 400 "Failed to load image" -- a burst of those on the
# live VPS flyers step. We sniff each fetched flyer's magic bytes and skip anything
# that isn't one of these supported raster types, and cap absurdly large payloads so
# one giant flyer can't blow the context/time budget.
SUPPORTED_IMAGE_MIME = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})
VISION_IMAGE_MAX_BYTES = int(os.getenv("VISION_IMAGE_MAX_BYTES", str(15 * 1024 * 1024)))


def sniff_image_mime(image_bytes: bytes) -> str | None:
    """Return the canonical mime for a supported raster image, or ``None``.

    Decides purely from the leading magic bytes (PNG ``\\x89PNG``, JPEG
    ``\\xff\\xd8\\xff``, GIF ``GIF8`` 7a/9a, RIFF/WEBP) -- authoritative even when a
    server mislabels the ``Content-Type``. ``None`` for HTML, PDF, empty, or any
    unrecognised payload, so the caller skips it instead of sending a non-image to
    the model."""
    if not image_bytes or len(image_bytes) < 12:
        return None
    b = image_bytes
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_flyer_image(
    image_bytes: bytes,
    *,
    content_type: str | None = None,
    max_bytes: int | None = None,
) -> tuple[str | None, str]:
    """Decide whether a fetched flyer payload is a raster image safe to send.

    Returns ``(mime, reason)``. ``mime`` is the canonical type to pass to the model
    when the payload is a supported raster image within the size cap; otherwise
    ``mime`` is ``None`` and ``reason`` says why (``empty`` / ``unsupported_type`` /
    ``too_large``) so the caller can log + skip rather than base64 a non-image into
    an ``image_url`` part (which makes the vision API 400). The decision is driven by
    magic-byte sniffing; ``content_type`` is advisory only (servers mislabel) and is
    kept for the skip log."""
    _ = content_type  # advisory; the magic-byte sniff is authoritative
    cap = VISION_IMAGE_MAX_BYTES if max_bytes is None else max_bytes
    if not image_bytes:
        return None, "empty"
    mime = sniff_image_mime(image_bytes)
    if mime is None:
        return None, "unsupported_type"
    if cap and len(image_bytes) > cap:
        return None, "too_large"
    return mime, "ok"


_MONTH_NAMES = (
    "January February March April May June July August September October "
    "November December"
).split()
MONTH_INDEX: dict[str, int] = {m.lower(): i + 1 for i, m in enumerate(_MONTH_NAMES)}
MONTH_INDEX.update({m.lower()[:3]: i + 1 for i, m in enumerate(_MONTH_NAMES)})


def vision_model() -> str:
    """Resolved vision model name.

    ``VISION_MODEL`` (generic) then ``PARKS_REC_VISION_MODEL`` (legacy alias)
    override the default. For a self-hosted backend set this to the served model
    name, e.g. ``qwen2.5vl:3b`` / ``minicpm-v`` / ``llama3.2-vision`` on Ollama.
    """
    return (
        (os.getenv("VISION_MODEL") or "").strip()
        or (os.getenv("PARKS_REC_VISION_MODEL") or "").strip()
        or DEFAULT_VISION_MODEL
    )


def _vision_client(openai_symbol: object):
    """Construct the vision client, or ``None`` when no backend is configured.

    Mirrors the local/openai split in :mod:`app.core.embeddings`:

    * ``VISION_BASE_URL`` set -> a **self-hosted OpenAI-compatible** endpoint
      (Ollama / vLLM / llama.cpp on your own VPS). No OpenAI key or spend; the
      ``VISION_API_KEY`` is optional (local servers ignore it, but the client
      needs a non-empty string). Constructed directly (not via the api_key-keyed
      singleton) so ``base_url`` is honored.
    * otherwise -> OpenAI, using ``OPENAI_API_KEY`` via the shared singleton.

    Returns ``None`` (caller degrades to "no events") when neither a local
    base URL nor an OpenAI key is available, or the ``openai`` package is absent.
    """
    if openai_symbol is None:
        return None
    base_url = (os.getenv("VISION_BASE_URL") or "").strip()
    if base_url:
        api_key = (os.getenv("VISION_API_KEY") or "").strip() or "local"
        return openai_symbol(
            api_key=api_key, base_url=base_url, timeout=LLM_CLIENT_READ_TIMEOUT_SEC
        )
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return None
    return get_openai_client(api_key, factory=openai_symbol, timeout=LLM_CLIENT_READ_TIMEOUT_SEC)


# --------------------------------------------------------------------------- #
# Row shape + validation stats
# --------------------------------------------------------------------------- #
@dataclass
class VisionEventRow:
    """One validated event the model read out of a calendar/flyer image."""

    title: str
    event_date: date
    start_time: time | None
    end_time: time | None
    location: str | None
    cost: str | None
    audience: str | None
    notes: str | None
    confidence: float
    source_cell: str
    # True when confidence < CONFIDENCE_THRESHOLD (or the self-check flagged the
    # date): the row must land hidden (draft=True + pending_review=True).
    should_hide: bool


@dataclass
class ValidationStats:
    """Per-image accounting of what the guards did, for the dry-run report."""

    raw: int = 0
    kept: int = 0
    held_low_confidence: int = 0
    dropped_out_of_month: int = 0
    dropped_no_provenance: int = 0
    dropped_bad_title: int = 0
    dropped_bad_date: int = 0


# --------------------------------------------------------------------------- #
# Field parsers (pure)
# --------------------------------------------------------------------------- #
_TIME_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?(?::(\d{2}))?\s*([ap]\.?m\.?)?\s*$", re.IGNORECASE)


def _clean_opt(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _parse_date(value: object) -> date | None:
    """Parse a ``YYYY-MM-DD`` (or date) value; ``None`` on anything else."""
    if isinstance(value, date):
        return value
    s = _clean_opt(value)
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


# Public alias: adapters month-bound flyer rows against each row's own parsed date.
parse_date = _parse_date


def _parse_time(value: object) -> time | None:
    """Parse ``HH:MM`` / ``H:MM`` / ``H:MM AM`` / ``9pm`` to a ``time``.

    The vision prompt asks for ``HH:MM`` (or null), but models drift to "9:00 AM"
    or "9pm"; this accepts those rather than dropping a real start time. Returns
    ``None`` for null/blank/garbage so the row lands "Time TBD" instead of with a
    fabricated clock value.
    """
    if isinstance(value, time):
        return value
    s = _clean_opt(value)
    if not s:
        return None
    m = _TIME_RE.match(s)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    second = int(m.group(3) or 0)
    meridiem = (m.group(4) or "").lower().replace(".", "")
    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return None
    return time(hour, minute, second)


def _clamp_confidence(value: object) -> float:
    try:
        c = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        # No usable confidence -> treat as low so the row is held, not trusted.
        return 0.0
    return max(0.0, min(1.0, c))


def validate_rows(
    raw_rows: list[dict],
    *,
    month: int,
    year: int,
) -> tuple[list[VisionEventRow], ValidationStats]:
    """Apply the §6 hallucination guards to raw model rows.

    Drops rows that fail month-bounding, provenance, title-shape, or date-parse;
    keeps the rest, marking sub-threshold confidence as ``should_hide``. Pure: no
    network, no DB -- the test suite drives every branch with recorded JSON.
    """
    stats = ValidationStats(raw=len(raw_rows))
    out: list[VisionEventRow] = []
    for r in raw_rows:
        if not isinstance(r, dict):
            continue
        title = _clean_opt(r.get("title"))
        if not title or len(title) > TITLE_MAX_LEN:
            stats.dropped_bad_title += 1
            continue
        # Provenance: the model must "show its work" -- a row with no verbatim
        # cell text is an invention and is dropped.
        source_cell = _clean_opt(r.get("source_cell"))
        if not source_cell:
            stats.dropped_no_provenance += 1
            continue
        d = _parse_date(r.get("date"))
        if d is None:
            stats.dropped_bad_date += 1
            continue
        # Month-bounding: the authoritative month/year comes from the image
        # TITLE, not from ``today`` -- a date outside it is a hallucination.
        if d.year != year or d.month != month:
            stats.dropped_out_of_month += 1
            continue
        conf = _clamp_confidence(r.get("confidence"))
        hide = conf < CONFIDENCE_THRESHOLD
        out.append(
            VisionEventRow(
                title=title,
                event_date=d,
                start_time=_parse_time(r.get("start_time")),
                end_time=_parse_time(r.get("end_time")),
                location=_clean_opt(r.get("location")),
                cost=_clean_opt(r.get("cost")),
                audience=_clean_opt(r.get("audience")),
                notes=_clean_opt(r.get("notes")),
                confidence=conf,
                source_cell=source_cell,
                should_hide=hide,
            )
        )
        stats.kept += 1
        if hide:
            stats.held_low_confidence += 1
    return out, stats


def apply_self_check_flags(
    rows: list[VisionEventRow],
    unsure_dates: set[date],
) -> int:
    """Demote any row whose date the self-check flagged as unsure to held.

    Returns the number of rows newly demoted. Pure -- the live second-pass call
    that produces ``unsure_dates`` lives in :func:`self_check_unsure_dates`.
    """
    demoted = 0
    for row in rows:
        if row.event_date in unsure_dates and not row.should_hide:
            row.should_hide = True
            demoted += 1
    return demoted


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #
def calendar_system_prompt(*, month: int, year: int) -> str:
    month_name = _MONTH_NAMES[month - 1]
    return (
        f"You are transcribing a printed monthly activities calendar for "
        f"{month_name} {year} from Lake Havasu City Parks & Recreation. Return "
        f"ONLY events you can actually read in the image. For each event return "
        f"the day number's full date in {year}-{month:02d}, the title verbatim, "
        f"start/end time if printed (else null), location/cost/audience/notes if "
        f"printed (else null), and the exact cell text you read in `source_cell`. "
        f"Do NOT infer, complete, or invent events, dates, times, or prices. If a "
        f"cell is blank or unreadable, skip it. If you are unsure of a value, set "
        f"it to null and lower `confidence` (0-1). Output strict JSON: "
        f'{{"events":[{{"title":...,"date":"YYYY-MM-DD","start_time":"HH:MM"|null,'
        f'"end_time":...,"location":...,"cost":...,"audience":...,"notes":...,'
        f'"confidence":0-1,"source_cell":...}}]}}.'
    )


def flyer_system_prompt(*, context_label: str) -> str:
    return (
        f"You are transcribing a single event flyer from {context_label}. The "
        f"flyer usually advertises ONE event (occasionally a short multi-day "
        f"series). Return ONLY what you can actually read: the title verbatim, "
        f"the full date in YYYY-MM-DD (use the year on the flyer; if none is "
        f"printed, set the date to null and lower confidence rather than "
        f"guessing), start/end time if printed (else null), and "
        f"location/cost/audience/notes if printed (else null), plus the exact "
        f"text you read in `source_cell`. Do NOT infer or invent dates, times, or "
        f"prices. Output strict JSON: "
        f'{{"events":[{{"title":...,"date":"YYYY-MM-DD"|null,"start_time":...,'
        f'"end_time":...,"location":...,"cost":...,"audience":...,"notes":...,'
        f'"confidence":0-1,"source_cell":...}}]}}.'
    )


# --------------------------------------------------------------------------- #
# Vision call (live; injectable for tests)
# --------------------------------------------------------------------------- #
def _data_url(image_bytes: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(image_bytes).decode("ascii")


def call_vision(
    image_bytes: bytes,
    *,
    system_prompt: str,
    model: str | None = None,
    mime: str = "image/png",
    openai_symbol: object = OpenAI,
) -> str:
    """Send one image to the vision model; return its raw text (``""`` on failure).

    Backend is chosen by env (see :func:`_vision_client`): a self-hosted
    OpenAI-compatible endpoint when ``VISION_BASE_URL`` is set (no token spend),
    else OpenAI via ``OPENAI_API_KEY``. Graceful no-op: returns ``""`` (one log
    line) when no backend is configured or the ``openai`` package is unavailable
    -- the caller treats ``""`` as "no events". The OpenAI symbol stays the
    patchable seam for tests.
    """
    client = _vision_client(openai_symbol)
    if client is None:
        logger.info("vision_calendar: no vision backend configured; returning empty extraction")
        return ""
    create_kwargs: dict = {
        "model": model or vision_model(),
        "temperature": 0,
        "response_format": {"type": "json_object"},
        # Cap the reply so a dense calendar's full event list fits (both backends).
        "max_tokens": VISION_MAX_TOKENS,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Transcribe every event you can read. Output strict "
                            'JSON {"events":[...]}.'
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": _data_url(image_bytes, mime)}},
                ],
            },
        ],
    }
    # num_ctx is Ollama-specific -> only on the self-hosted path. The image eats
    # most of the default window, so without this the output truncates mid-JSON.
    if (os.getenv("VISION_BASE_URL") or "").strip():
        create_kwargs["extra_body"] = {"options": {"num_ctx": VISION_NUM_CTX}}
    try:
        resp = client.chat.completions.create(**create_kwargs)
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        logger.exception("vision_calendar: vision call failed")
        return ""


def self_check_unsure_dates(
    image_bytes: bytes,
    rows: list[VisionEventRow],
    *,
    month: int,
    year: int,
    model: str | None = None,
    mime: str = "image/png",
    openai_symbol: object = OpenAI,
) -> set[date]:
    """Cheap second pass: ask the model which of the read dates it is unsure of.

    Returns the set of dates to demote to held. Best-effort -- any failure (no
    key, bad JSON) returns the empty set so the first pass stands.
    """
    if not rows:
        return set()
    listed = ", ".join(sorted({r.event_date.isoformat() for r in rows}))
    prompt = (
        f"You previously read {len(rows)} events from this {_MONTH_NAMES[month - 1]} "
        f"{year} calendar on these dates: {listed}. Re-examine the image and list "
        f"ONLY the dates you are NOT confident are correct. Output strict JSON: "
        f'{{"unsure_dates":["YYYY-MM-DD", ...]}} (empty list if all are correct).'
    )
    raw = call_vision(
        image_bytes, system_prompt=prompt, model=model, mime=mime, openai_symbol=openai_symbol
    )
    if not raw:
        return set()
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return set()
    out: set[date] = set()
    for v in (data or {}).get("unsure_dates", []) if isinstance(data, dict) else []:
        d = _parse_date(v)
        if d is not None:
            out.add(d)
    return out


# --------------------------------------------------------------------------- #
# Parse + orchestrate
# --------------------------------------------------------------------------- #
def _salvage_truncated_events(raw_text: str) -> list[dict]:
    """Recover the complete event objects from a truncated JSON reply.

    A small CPU model frequently runs out of context mid-array on a dense calendar,
    so ``json.loads`` fails on an otherwise-good ``{"events":[ {..}, {..}, {<cut>``.
    Rather than drop every event the model *did* read, walk the array and keep each
    balanced, individually-parseable ``{...}`` object; stop at the first incomplete
    one. Returns ``[]`` if there's no recognizable array to walk.
    """
    head = raw_text.find('"events"')
    start = raw_text.find("[", head) if head != -1 else raw_text.find("[")
    if start == -1:
        return []
    rows: list[dict] = []
    depth = 0
    in_str = False
    esc = False
    obj_start = -1
    for j in range(start + 1, len(raw_text)):
        c = raw_text[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            if depth == 0:
                obj_start = j
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and obj_start != -1:
                try:
                    d = json.loads(raw_text[obj_start : j + 1])
                    if isinstance(d, dict):
                        rows.append(d)
                except ValueError:
                    pass
                obj_start = -1
        elif c == "]" and depth == 0:
            break
    return rows


def parse_events_json(raw_text: str) -> list[dict]:
    """Parse the model's strict-JSON reply into a list of row dicts.

    Accepts ``{"events":[...]}`` or a bare ``[...]``; on a parse failure (almost
    always a truncated reply) it salvages the complete objects read so far rather
    than dropping the whole tile. Returns ``[]`` only on an unexpected shape.
    """
    if not raw_text:
        return []
    try:
        data = json.loads(raw_text)
    except (ValueError, TypeError):
        # Non-empty but unparseable is almost always a truncated reply (the model
        # ran out of context emitting a long event list). Salvage what completed --
        # a silent [] here is what made truncation look like "the model read
        # nothing" -- and log loudly so the cause stays visible.
        salvaged = _salvage_truncated_events(raw_text)
        logger.warning(
            "vision_calendar: %d chars of model output failed to parse "
            "(likely truncated -- raise VISION_CALENDAR_TILES); salvaged %d complete "
            "event(s); head=%r",
            len(raw_text),
            len(salvaged),
            raw_text[:120],
        )
        return salvaged
    if isinstance(data, dict):
        rows = data.get("events")
    elif isinstance(data, list):
        rows = data
    else:
        rows = None
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


@dataclass
class ExtractionResult:
    rows: list[VisionEventRow] = field(default_factory=list)
    stats: ValidationStats = field(default_factory=ValidationStats)
    raw_text: str = ""


def extract_validated_rows(
    image_bytes: bytes,
    *,
    system_prompt: str,
    month: int,
    year: int,
    model: str | None = None,
    mime: str = "image/png",
    openai_symbol: object = OpenAI,
    raw_text: str | None = None,
    self_check: bool = False,
) -> ExtractionResult:
    """Full engine: (vision call ->) parse -> validate (-> self-check demote).

    Tests pass ``raw_text`` to inject recorded model JSON and skip the live call
    entirely. ``self_check`` enables the cheap confirm-dates second pass (live
    only; it needs the image bytes and the key).
    """
    text = (
        raw_text
        if raw_text is not None
        else call_vision(
            image_bytes,
            system_prompt=system_prompt,
            model=model,
            mime=mime,
            openai_symbol=openai_symbol,
        )
    )
    rows, stats = validate_rows(parse_events_json(text), month=month, year=year)
    if self_check and rows and raw_text is None:
        unsure = self_check_unsure_dates(
            image_bytes, rows, month=month, year=year, model=model, mime=mime,
            openai_symbol=openai_symbol,
        )
        demoted = apply_self_check_flags(rows, unsure)
        stats.held_low_confidence += demoted
    return ExtractionResult(rows=rows, stats=stats, raw_text=text)


# --------------------------------------------------------------------------- #
# Tiling -- split a dense calendar so each request stays small (CPU-friendly)
# --------------------------------------------------------------------------- #
def _dedup_title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def split_image_vertically(
    image_bytes: bytes,
    *,
    n_tiles: int,
    overlap_frac: float = VISION_CALENDAR_TILE_OVERLAP,
) -> list[bytes]:
    """Crop ``image_bytes`` into ``n_tiles`` overlapping horizontal bands (PNG each).

    Bands overlap by ``overlap_frac`` of a band so an event row straddling a tile
    boundary still appears whole in at least one tile; :func:`merge_dedup_rows`
    drops the overlap. Returns ``[image_bytes]`` unchanged when ``n_tiles <= 1`` or
    Pillow / decoding is unavailable (the caller then runs the un-tiled path).
    """
    if n_tiles <= 1:
        return [image_bytes]
    try:
        import io

        from PIL import Image
    except Exception:  # pragma: no cover -- Pillow present in prod
        return [image_bytes]
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
        img = img.convert("RGB")
    except Exception:
        logger.exception("vision_calendar: image decode failed; not tiling")
        return [image_bytes]
    w, h = img.size
    if h < n_tiles * 2:  # too small to split meaningfully
        return [image_bytes]
    band = h / n_tiles
    over = band * max(0.0, overlap_frac)
    tiles: list[bytes] = []
    for i in range(n_tiles):
        top = max(0, int(i * band - over))
        bottom = min(h, int((i + 1) * band + over))
        buf = io.BytesIO()
        img.crop((0, top, w, bottom)).save(buf, format="PNG")
        tiles.append(buf.getvalue())
    return tiles


def merge_dedup_rows(row_lists: list[list[VisionEventRow]]) -> tuple[list[VisionEventRow], int]:
    """Flatten tile results and dedup by ``(date, normalized title)``.

    Keeps the higher-confidence row of a duplicate pair (the overlap band sees the
    same event twice). Returns ``(rows, num_duplicates_dropped)``; input order is
    otherwise preserved.
    """
    best: dict[tuple[date, str], VisionEventRow] = {}
    order: list[tuple[date, str]] = []
    dups = 0
    for rows in row_lists:
        for r in rows:
            key = (r.event_date, _dedup_title_key(r.title))
            cur = best.get(key)
            if cur is None:
                best[key] = r
                order.append(key)
            else:
                dups += 1
                if r.confidence > cur.confidence:
                    best[key] = r
    return [best[k] for k in order], dups


def extract_calendar_tiled(
    image_bytes: bytes,
    *,
    system_prompt: str,
    month: int,
    year: int,
    n_tiles: int,
    model: str | None = None,
    mime: str = "image/png",
    openai_symbol: object = OpenAI,
    raw_text_by_tile: dict[int, str] | None = None,
) -> ExtractionResult:
    """Tiled calendar extraction: split -> validate each tile -> merge + dedup.

    The calendar's title-derived ``month``/``year`` bounds every tile (same grid).
    Tests inject ``raw_text_by_tile`` (tile index -> recorded JSON) to skip the live
    call. Stats are aggregated across tiles; ``kept`` is the post-dedup count.
    """
    tiles = split_image_vertically(image_bytes, n_tiles=n_tiles)
    agg = ValidationStats()
    per_tile: list[list[VisionEventRow]] = []
    raw_parts: list[str] = []
    for idx, tile in enumerate(tiles):
        rt = (raw_text_by_tile or {}).get(idx) if raw_text_by_tile is not None else None
        text = (
            rt
            if rt is not None
            else call_vision(
                tile, system_prompt=system_prompt, model=model, mime="image/png",
                openai_symbol=openai_symbol,
            )
        )
        raw_parts.append(text)
        rows, stats = validate_rows(parse_events_json(text), month=month, year=year)
        per_tile.append(rows)
        agg.raw += stats.raw
        agg.dropped_out_of_month += stats.dropped_out_of_month
        agg.dropped_no_provenance += stats.dropped_no_provenance
        agg.dropped_bad_title += stats.dropped_bad_title
        agg.dropped_bad_date += stats.dropped_bad_date
    merged, _dups = merge_dedup_rows(per_tile)
    agg.kept = len(merged)
    agg.held_low_confidence = sum(1 for r in merged if r.should_hide)
    return ExtractionResult(
        rows=merged, stats=agg, raw_text="\n---TILE---\n".join(raw_parts)
    )


# Flyers usually omit the YEAR, so the model fills a training-prior one (e.g. 2023
# for a 2026 event). Unlike the calendar, a flyer has no title-derived year to bound
# against. A flyer date this many days in the past is treated as a wrong-year guess
# and rolled forward to the nearest future occurrence of its month/day.
VISION_FLYER_PAST_GRACE_DAYS = int(os.getenv("VISION_FLYER_PAST_GRACE_DAYS", "45"))


def _roll_year_forward(d: date, today: date) -> date:
    """Nearest date >= ``today`` sharing ``d``'s month/day (this year or next)."""
    for yr in (today.year, today.year + 1, today.year + 2):
        try:
            cand = d.replace(year=yr)
        except ValueError:  # Feb 29 in a non-leap year
            continue
        if cand >= today:
            return cand
    return d


def correct_flyer_years(
    rows: list[VisionEventRow],
    *,
    today: date,
    grace_days: int = VISION_FLYER_PAST_GRACE_DAYS,
) -> int:
    """Roll implausibly-past flyer dates forward to the nearest future year.

    A flyer on the Current-Events page advertises an UPCOMING event, so a date more
    than ``grace_days`` before ``today`` is almost certainly a missing-year guess.
    Rewrites such rows in place to the nearest future month/day; returns the count
    corrected. Pure. (The calendar path never calls this -- its year is authoritative
    from the image title.)
    """
    cutoff = today - timedelta(days=max(0, grace_days))
    corrected = 0
    for r in rows:
        if r.event_date < cutoff:
            new = _roll_year_forward(r.event_date, today)
            if new != r.event_date:
                r.event_date = new
                corrected += 1
    return corrected


def extract_flyer_rows(
    image_bytes: bytes,
    *,
    context_label: str,
    mime: str = "image/png",
    model: str | None = None,
    openai_symbol: object = OpenAI,
    raw_text: str | None = None,
    today: date | None = None,
) -> ExtractionResult:
    """Engine entry for a single flyer image (one event, occasionally a series).

    A flyer has no authoritative month grid, so each row is month-bounded against
    the month/year of its OWN parsed date -- a stray hallucinated second date is
    still dropped. Implausibly-past dates (missing-year guesses) are rolled forward
    via :func:`correct_flyer_years`. Shared by every flyer adapter (Parks & Rec,
    senior center) so the guard logic lives in one place. Tests inject ``raw_text``
    and ``today``.
    """
    text = (
        raw_text
        if raw_text is not None
        else call_vision(
            image_bytes,
            system_prompt=flyer_system_prompt(context_label=context_label),
            model=model,
            mime=mime,
            openai_symbol=openai_symbol,
        )
    )
    raw_rows = parse_events_json(text)
    kept: list[VisionEventRow] = []
    stats = ValidationStats(raw=len(raw_rows))
    for r in raw_rows:
        d = parse_date(r.get("date")) if isinstance(r, dict) else None
        if d is None:
            stats.dropped_bad_date += 1
            continue
        rows, sub = validate_rows([r], month=d.month, year=d.year)
        kept.extend(rows)
        stats.kept += sub.kept
        stats.held_low_confidence += sub.held_low_confidence
        stats.dropped_no_provenance += sub.dropped_no_provenance
        stats.dropped_bad_title += sub.dropped_bad_title
        stats.dropped_out_of_month += sub.dropped_out_of_month
    correct_flyer_years(kept, today=today or date.today())
    return ExtractionResult(rows=kept, stats=stats, raw_text=text)


__all__ = [
    "CONFIDENCE_THRESHOLD",
    "DEFAULT_VISION_MODEL",
    "VISION_CALENDAR_TILES",
    "VISION_MAX_TOKENS",
    "VISION_NUM_CTX",
    "VISION_FLYER_PAST_GRACE_DAYS",
    "correct_flyer_years",
    "extract_calendar_tiled",
    "merge_dedup_rows",
    "split_image_vertically",
    "ExtractionResult",
    "MONTH_INDEX",
    "SUPPORTED_IMAGE_MIME",
    "VISION_IMAGE_MAX_BYTES",
    "ValidationStats",
    "VisionEventRow",
    "apply_self_check_flags",
    "calendar_system_prompt",
    "call_vision",
    "extract_flyer_rows",
    "sniff_image_mime",
    "validate_flyer_image",
    "extract_validated_rows",
    "flyer_system_prompt",
    "parse_date",
    "parse_events_json",
    "self_check_unsure_dates",
    "validate_rows",
    "vision_model",
]
