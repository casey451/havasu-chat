"""Schedule drift checker — fingerprint stability + change detection."""

from __future__ import annotations

from scripts.schedule_drift_check import fingerprint, load_sources

_PAGE = """
<html><head><script>var nonce="abc123";</script>
<style>.x{color:red}</style></head>
<body><h1>Class   Schedule</h1>
<p>Mon 6:00 PM  BJJ Fundamentals</p>
<img src="https://static.wixstatic.com/media/sched_v1.png?w=800">
</body></html>
"""


def test_text_fingerprint_ignores_scripts_styles_and_whitespace() -> None:
    noisy = _PAGE.replace('nonce="abc123"', 'nonce="zzz999"').replace(
        "Class   Schedule", "Class\n\n  Schedule"
    )
    assert fingerprint(_PAGE, "text") == fingerprint(noisy, "text")


def test_text_fingerprint_changes_when_times_change() -> None:
    changed = _PAGE.replace("Mon 6:00 PM", "Mon 7:00 PM")
    assert fingerprint(_PAGE, "text") != fingerprint(changed, "text")


def test_image_urls_fingerprint_ignores_text_but_sees_image_swap() -> None:
    text_changed = _PAGE.replace("Mon 6:00 PM", "Tue 8:00 AM")
    assert fingerprint(_PAGE, "image_urls") == fingerprint(text_changed, "image_urls")
    img_changed = _PAGE.replace("sched_v1.png", "sched_v2.png")
    assert fingerprint(_PAGE, "image_urls") != fingerprint(img_changed, "image_urls")


def test_image_urls_fingerprint_strips_query_strings() -> None:
    resized = _PAGE.replace("sched_v1.png?w=800", "sched_v1.png?w=1200")
    assert fingerprint(_PAGE, "image_urls") == fingerprint(resized, "image_urls")


def test_load_sources_covers_all_captured_venues_with_modes() -> None:
    sources = load_sources()
    names = {n for n, _, _ in sources}
    assert len(sources) == 17
    assert "Bridge City Combat" in names
    by_name = {n: (u, m) for n, u, m in sources}
    # image-based venues use the image_urls mode
    assert by_name["Bridge City Combat"][1] == "image_urls"
    assert by_name["Ballet Havasu"][1] == "image_urls"
    # Elite's URL override (broken HTTPS cert upstream)
    assert by_name["Elite Martial Arts Inc"][0].startswith("http://www.")
    # Strength gyms added 2026-06-27 — web schedules, so plain text-mode drift.
    for gym in ("Havasu CrossFit", "Fit Lab 928", "Feelin' Good Fitness"):
        assert by_name[gym][1] == "text"
