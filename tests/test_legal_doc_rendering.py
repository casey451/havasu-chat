"""Markdown→HTML renderer for /privacy + /terms (wrapped bullets, comments).

Regression suite for the live bug where every hard-wrapped bullet on /privacy
split mid-sentence: the renderer emitted one <li> per SOURCE LINE, so a
bullet's indented continuation line closed the list and became an orphan <p>
("…to improve the</li></ul><p>service, fix bugs…"). Also covers: HTML source
comments must not ship to the public page (the live /terms exposed the
"Drafted by AI … needs attorney review" note in page source), and the
events-permalink "passed" banner must not fire the minute a no-end-time event
starts.
"""

from __future__ import annotations

from datetime import date, time, timedelta
from types import SimpleNamespace

from app.core.timezone import now_lake_havasu
from app.main import _event_is_past, _render_doc_markdown_to_html


def test_wrapped_bullet_stays_one_li():
    md = (
        "## What we collect\n"
        "\n"
        "- **Your chat messages and our responses** — to improve the\n"
        "  service, fix bugs, and catch gaps in what we cover.\n"
        "- **Your session ID** — a random identifier generated per visit.\n"
        "  It doesn't tie to any identity or personal information.\n"
    )
    out = _render_doc_markdown_to_html(md)
    assert out.count("<li>") == 2
    assert out.count("<ul>") == 1
    # The continuation text lives INSIDE the bullet, not in an orphan <p>.
    assert "service, fix bugs, and catch gaps" in out
    assert "<p>service" not in out
    assert "to improve the service, fix bugs" in out.replace("</strong>", "").replace(
        "<strong>", ""
    ).replace("\n", " ").replace("  ", " ") or "to improve the\nservice" not in out


def test_unwrapped_bullets_unchanged():
    md = "- Anthropic: https://www.anthropic.com/privacy\n- OpenAI: https://openai.com/privacy\n"
    out = _render_doc_markdown_to_html(md)
    assert out.count("<li>") == 2


def test_new_bullet_ends_previous_item():
    md = "- first item\n- second item\n"
    out = _render_doc_markdown_to_html(md)
    assert out.count("<li>") == 2
    assert "first item" in out and "second item" in out


def test_blank_line_still_closes_list():
    md = "- only item\n\nA paragraph after the list.\n"
    out = _render_doc_markdown_to_html(md)
    assert out.count("<li>") == 1
    assert "<p>A paragraph after the list.</p>" in out


def test_html_comments_do_not_ship():
    md = "<!-- Drafted by AI — needs attorney review -->\n# Terms\n\nBody text.\n"
    out = _render_doc_markdown_to_html(md)
    assert "Drafted by AI" not in out
    assert "<h1>Terms</h1>" in out


def _event(**kw):
    base = dict(
        rdate=None,
        date=None,
        end_date=None,
        start_time=None,
        end_time=None,
        rrule=None,
        is_recurring=False,
        exdate=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_no_end_time_event_not_past_right_after_start():
    now = now_lake_havasu()
    started_45_min_ago = (
        (now - timedelta(minutes=45)).time().replace(second=0, microsecond=0)
    )
    ev = _event(date=now.date(), start_time=started_45_min_ago)
    assert _event_is_past(ev) is False


def test_no_end_time_same_day_event_not_past_until_end_of_day():
    # New contract (fix 1.3): a same-day event with no end_time is NOT marked
    # "passed" just because some hours have elapsed — it stays current until the
    # end of the local day. (Previously it flipped to past after a ~3-hour grace,
    # which prematurely hid morning/all-day events from the detail page.)
    now = now_lake_havasu()
    if now.hour < 5:  # ensure "4h ago" is still earlier the same local day
        return
    started_4_h_ago = (now - timedelta(hours=4)).time().replace(second=0, microsecond=0)
    ev = _event(date=now.date(), start_time=started_4_h_ago)
    assert _event_is_past(ev) is False


def test_explicit_end_time_still_authoritative():
    now = now_lake_havasu()
    if now.hour < 2:
        return
    ended = (now - timedelta(hours=1)).time().replace(second=0, microsecond=0)
    ev = _event(date=now.date(), start_time=time(6, 0), end_time=ended)
    assert _event_is_past(ev) is True


def test_yesterday_is_past_and_tomorrow_is_not():
    today = now_lake_havasu().date()
    assert _event_is_past(_event(date=today - timedelta(days=1))) is True
    assert _event_is_past(_event(date=today + timedelta(days=1))) is False
    assert _event_is_past(_event(date=date(2030, 1, 1))) is False
