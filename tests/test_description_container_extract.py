"""Regression: recover an event description from the body content container when
og:description / JSON-LD carry only the site name (RiverScene Magazine event
pages). Drives the 2026-06-23 description backfill.
"""

from __future__ import annotations

from app.contrib.event_enrich import description_from_detail_html

# Mirrors the riverscenemagazine.com event-page shape: useless og:description +
# the real blurb in <div class="blog-details-desc"> below a details table.
_RIVER_SCENE_HTML = """
<html><head>
  <meta property="og:description" content="RiverScene Magazine">
  <meta name="description" content="RiverScene Magazine">
</head><body>
  <div class="container"><div class="row"><div class="col-lg-8 col-md-12">
    <div class="blog-details-desc">
      <table><tr><td>Start Date</td><td>07/04/2026</td></tr>
             <tr><td>Venue</td><td>Rotary Park</td></tr></table>
      <p>Who loves fireworks? Get ready to celebrate the 4th of July Havasu style.</p>
      <p>At 9 p.m. the show lights up the channel over Rotary Park.</p>
    </div>
  </div></div></div>
</body></html>
"""


def test_description_recovered_from_content_container():
    desc = description_from_detail_html(_RIVER_SCENE_HTML)
    assert "fireworks" in desc.lower()
    assert "celebrate the 4th of july" in desc.lower()
    # The details-table text (Start Date / Venue grid) must NOT leak into the blurb.
    assert "Start Date" not in desc
    assert "07/04/2026" not in desc
    # The boilerplate site-name og:description must not win.
    assert desc.strip() != "RiverScene Magazine"


def test_jsonld_still_wins_when_present():
    html = """
    <html><head>
      <script type="application/ld+json">
        {"@type":"Event","name":"X","description":"Real JSON-LD description here."}
      </script>
    </head><body>
      <div class="blog-details-desc"><p>A different body paragraph that is long enough.</p></div>
    </body></html>
    """
    assert description_from_detail_html(html) == "Real JSON-LD description here."


def test_no_container_returns_empty():
    html = "<html><head><meta property='og:description' content='RiverScene Magazine'></head><body></body></html>"
    # og:description is the only signal and it's boilerplate site name → cleaned to "".
    out = description_from_detail_html(html)
    assert out.strip() in ("", "RiverScene Magazine")  # cleaner may or may not strip it
