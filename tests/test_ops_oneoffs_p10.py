"""Phase 10 (consolidated Amendment) — ops one-offs.

* out-of-town news items get an honest region label (§6.2);
* movie poster tiles fall back to the title card when the image fails (§6.3);
* the gas cheapest-card never pairs a mismatched brand with a station name
  (§6.4);
* /contribute uses a real em-dash (F16 leftover, §6.11).
"""

from __future__ import annotations

from pathlib import Path

from app.news.store import _region_label

_ROOT = Path(__file__).resolve().parents[1]


# --- news region labels ---------------------------------------------------------


def test_out_of_town_headlines_get_region_label():
    assert _region_label("Horseshoe tournament July 4 at Manataba Park") == "Parker"
    assert _region_label("Blood Drive July 8 at La Paz Hospital") == "Parker"
    assert _region_label("Parker girls' softball all-stars advance") == "Parker"
    assert _region_label("Kingman council adopts budget") == "Kingman"
    assert _region_label("Bullhead City announces road closures") == "Bullhead City"


def test_havasu_headlines_stay_unlabeled():
    assert _region_label("Lake Havasu City council adopts budget") is None
    assert _region_label("New restaurant opens on McCulloch") is None
    # A Havasu story that mentions a neighbor is still local news.
    assert _region_label("Lake Havasu team beats Parker in regional final") is None
    # Parker DAM is the local landmark, not the town.
    assert _region_label("Water releases increase at Parker Dam") is None


# --- template-level checks --------------------------------------------------------


def test_movie_poster_has_failure_fallback():
    # v4.5: /movies renders movies_redesign.html (the old movies_body.html was
    # swept in PR-7). The fallback-before-img ordering contract is preserved.
    tpl = (_ROOT / "app" / "templates" / "movies_redesign.html").read_text(
        encoding="utf-8"
    )
    assert 'onerror="this.remove()"' in tpl
    # The title card renders unconditionally behind the poster.
    assert tpl.index("mvposter-fallback") < tpl.index("mvposter-img")


def test_gas_card_brand_never_contradicts_name():
    tpl = (_ROOT / "app" / "templates" / "gas_prices_lake.html").read_text(
        encoding="utf-8"
    )
    # M12 (2026-07-08): the "Cheapest today" gas-card strip — and its brand line —
    # was removed; the price-sorted "All stations" table shows plain station names.
    assert 'class="gas-cheap"' not in tpl  # the ranked-card strip is gone
    assert "{{ s.brand or s.name }}" not in tpl  # the old contradictory line, still out


def test_contribute_uses_em_dash():
    # v4.6: the /contribute copy moved from the inline Python page into the Jinja
    # template (contribute_redesign.html) when it migrated onto the v4 shell.
    tpl = (_ROOT / "app" / "templates" / "contribute_redesign.html").read_text(
        encoding="utf-8"
    )
    assert "submission -- never" not in tpl
    assert "submission — never" in tpl
