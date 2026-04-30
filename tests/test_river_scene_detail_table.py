"""River Scene Event Details table: two-pass ``_table_label_map`` and public URL precedence."""

from __future__ import annotations

from datetime import date, time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from bs4 import BeautifulSoup

from app.contrib.river_scene import (
    RIVER_SCENE_DETAIL_LABELS,
    RiverSceneEvent,
    _find_event_details_table,
    _submission_public_url,
    _table_label_map,
    fetch_and_parse_event,
    normalize_to_contribution,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "river_scene"


@pytest.fixture(autouse=True)
def _no_polite_sleep() -> None:
    with patch("app.contrib.river_scene._sleep_polite"):
        yield


def _labels_from_html_fragment(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    table = _find_event_details_table(soup)
    assert table is not None
    return _table_label_map(table)


def test_detail_labels_allowlist_size() -> None:
    assert len(RIVER_SCENE_DETAIL_LABELS) == 8


def test_table_label_map_proper_website_and_facebook_water_x_shape() -> None:
    html = """
    <html><body><table><tbody>
    <tr><td>Start Date</td><td>April 10, 2026</td></tr>
    <tr><td>End Date</td><td>April 12, 2026</td></tr>
    <tr><td>Organizer</td><td>Nauti Water Racing</td></tr>
    <tr><td>Facebook</td><td><a href="https://www.facebook.com/officialnautiwaterracing">https://www.facebook.com/officialnautiwaterracing</a></td></tr>
    <tr><td>Website</td><td><a href="https://nautiwaterracing.com/schedule/">https://nautiwaterracing.com/schedule/</a></td></tr>
    <tr><td>Event Category</td><td>on the lake</td></tr>
    <tr><td>Venue</td><td>Windsor 4</td></tr>
    </tbody></table></body></html>
    """
    labels = _labels_from_html_fragment(html)
    assert labels["Website"] == "https://nautiwaterracing.com/schedule/"
    assert labels["Facebook"] == "https://www.facebook.com/officialnautiwaterracing"


def test_table_label_map_orphan_td_website_taste_shape() -> None:
    html = """
    <html><body><table><tbody>
    <tr><td>Start Date</td><td>October 22, 2026</td></tr>
    <tr><td>Organizer</td><td>K-12 Foundation</td></tr>
    <td>Website</td><td><a href="https://www.k12foundation.org">https://www.k12foundation.org</a></td></tr>
    <tr><td>Venue</td><td>Sara Park</td></tr>
    </tbody></table></body></html>
    """
    labels = _labels_from_html_fragment(html)
    assert labels.get("Website") == "https://www.k12foundation.org"


def test_table_label_map_multiple_orphan_detail_labels() -> None:
    """Two orphan pairs (Website + Facebook) both recovered by pass 2."""
    html = """
    <html><body><table><tbody>
    <tr><td>Start Date</td><td>March 1, 2027</td></tr>
    <tr><td>Organizer</td><td>Org</td></tr>
    <td>Website</td><td><a href="https://web.example/event">go</a></td></tr>
    <td>Facebook</td><td><a href="https://www.facebook.com/events/999">fb</a></td></tr>
    <tr><td>Venue</td><td>Here</td></tr>
    </tbody></table></body></html>
    """
    labels = _labels_from_html_fragment(html)
    assert labels["Website"] == "https://web.example/event"
    assert labels["Facebook"] == "https://www.facebook.com/events/999"


def test_table_label_map_pass_one_wins_over_pass_two() -> None:
    html = """
    <html><body><table><tbody>
    <tr><td>Start Date</td><td>January 1, 2027</td></tr>
    <tr><td>Website</td><td><a href="https://first.example/">first</a></td></tr>
    <tr><td>Organizer</td><td>O</td></tr>
    </tr>
    <td>Website</td><td><a href="https://orphan-wrong.example/">wrong</a></td></tr>
    </tbody></table></body></html>
    """
    labels = _labels_from_html_fragment(html)
    assert labels["Website"] == "https://first.example/"


def test_table_label_map_decoy_table_does_not_pollute() -> None:
    """Pass 2 is scoped to the Start Date–anchored table only."""
    html = """
    <html><body>
    <table><tr><td>Website</td><td>http://decoy.example/</td></tr></table>
    <table><tbody>
    <tr><td>Start Date</td><td>February 2, 2027</td></tr>
    <tr><td>Website</td><td><a href="https://real.example/">real</a></td></tr>
    </tbody></table>
    </body></html>
    """
    labels = _labels_from_html_fragment(html)
    assert labels["Website"] == "https://real.example/"
    assert "decoy" not in labels["Website"]


def test_table_label_map_facebook_plain_text_without_anchor() -> None:
    html = """
    <html><body><table><tbody>
    <tr><td>Start Date</td><td>April 1, 2027</td></tr>
    <tr><td>Facebook</td><td>www.facebook.com/plain.example/page</td></tr>
    </tbody></table></body></html>
    """
    labels = _labels_from_html_fragment(html)
    assert "facebook.com/plain.example/page" in labels["Facebook"]


def test_submission_public_url_website_then_facebook_then_article() -> None:
    article = "https://riverscenemagazine.com/events/x/"
    base = dict(
        title="T",
        url=article,
        start_date=date(2026, 6, 15),
        end_date=date(2026, 6, 15),
        start_time=time(9, 0),
        end_time=time(9, 0),
        description_html="",
        venue_name=None,
        venue_address=None,
        organizer=None,
        category_slugs=[],
    )
    only_fb = RiverSceneEvent(**base, raw={"labels": {"Facebook": "https://www.facebook.com/events/1"}})
    assert _submission_public_url(only_fb) == "https://www.facebook.com/events/1"

    both = RiverSceneEvent(
        **base,
        raw={"labels": {"Website": "https://site.example/", "Facebook": "https://www.facebook.com/events/2"}},
    )
    assert _submission_public_url(both) == "https://site.example/"

    empty = RiverSceneEvent(**base, raw={"labels": {}})
    assert _submission_public_url(empty) == article


def test_submission_public_url_scheme_normalized_like_website() -> None:
    rse = RiverSceneEvent(
        title="T",
        url="https://riverscenemagazine.com/events/z/",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 1),
        start_time=time(10, 0),
        end_time=time(10, 0),
        description_html="",
        venue_name=None,
        venue_address=None,
        organizer=None,
        category_slugs=[],
        raw={"labels": {"Facebook": "www.facebook.com/events/scheme"}},
    )
    assert _submission_public_url(rse) == "https://www.facebook.com/events/scheme"


def test_normalize_prefers_website_over_facebook_for_submission_url() -> None:
    rse = RiverSceneEvent(
        title="T",
        url="https://riverscenemagazine.com/events/both/",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 1),
        start_time=time(11, 0),
        end_time=time(11, 0),
        description_html="",
        venue_name=None,
        venue_address=None,
        organizer=None,
        category_slugs=[],
        raw={
            "labels": {
                "Website": "https://primary.example/",
                "Facebook": "https://www.facebook.com/events/understudy",
            }
        },
    )
    payload = normalize_to_contribution(rse)
    assert str(payload.submission_url) == "https://primary.example/"


def test_fetch_parse_taste_fixture_submission_url_k12() -> None:
    html = (FIXTURES / "2026-taste-of-havasu-event-details.html").read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        rse = fetch_and_parse_event(
            "https://riverscenemagazine.com/events/2026-taste-of-havasu/",
            client=client,
            today=date(2026, 1, 1),
        )
    assert rse is not None
    assert _submission_public_url(rse) == "https://www.k12foundation.org"
    payload = normalize_to_contribution(rse)
    assert str(payload.submission_url).rstrip("/") == "https://www.k12foundation.org"


def test_fetch_parse_won_bass_fixture_submission_url_facebook() -> None:
    html = (FIXTURES / "won-bass-havasu-event-details.html").read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        rse = fetch_and_parse_event(
            "https://riverscenemagazine.com/events/won-bass-havasu/",
            client=client,
            today=date(2026, 1, 1),
        )
    assert rse is not None
    assert _submission_public_url(rse) == "https://www.facebook.com/events/982632057401700"
    payload = normalize_to_contribution(rse)
    assert str(payload.submission_url) == "https://www.facebook.com/events/982632057401700"
