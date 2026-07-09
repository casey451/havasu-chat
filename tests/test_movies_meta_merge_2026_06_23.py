"""Movies — one canonical rating/runtime/genre per film across theaters.

Phase 2.3 (FIX_SPEC_2026-06-23). Live bug: the same film read differently under
each theater — "The Death of Robin Hood" (2h 3m) vs "…Of…" (2h 2m), different
genres. ``group_showtimes`` canonicalized the title but took meta from the first
row per theater. Now metadata is merged per film: longest genre, single
canonical-source runtime, first rating by theater order.
"""

from __future__ import annotations

from datetime import date, time

from app.db.models import MovieShowtime
from app.movies.queries import group_showtimes

DAY = date(2099, 7, 1)


def ms(
    title: str, slug: str, name: str, hh: int, *,
    rating: str = "R", genre: str = "Action", runtime: int = 120,
) -> MovieShowtime:
    return MovieShowtime(
        source="test", source_stable_id=f"{title}-{hh}-{slug}",
        theater_slug=slug, theater_name=name, film_title=title,
        show_date=DAY, show_time=time(hh, 0),
        rating=rating, genre=genre, runtime_minutes=runtime,
        poster_url="http://p.jpg", booking_url="http://book",
    )


def _film_in(groups, slug):
    grp = next(g for g in groups if g.slug == slug)
    assert len(grp.films) == 1
    return grp.films[0]


def test_meta_merged_consistently_across_theaters() -> None:
    rows = [
        # Star Cinemas (canonical source): shorter genre, runtime 123.
        ms("The Death of Robin Hood", "star-cinemas", "Star Cinemas", 14,
           genre="Action", runtime=123),
        # Movies Havasu: different casing, longer genre, runtime 122.
        ms("The Death Of Robin Hood", "movies-havasu", "Movies Havasu", 19,
           genre="Action, Adventure", runtime=122),
    ]
    groups = group_showtimes(rows, day=DAY)
    star = _film_in(groups, "star-cinemas")
    havasu = _film_in(groups, "movies-havasu")

    # Same canonical title in both sections (Star spelling wins).
    assert star.title == "The Death of Robin Hood"
    assert havasu.title == "The Death of Robin Hood"
    # Identical merged meta in BOTH theater sections: longest genre + canonical
    # (Star) runtime.
    assert star.meta == "Action, Adventure · 2h 3m"
    assert havasu.meta == star.meta
    assert star.rating == havasu.rating == "R"


def test_runtime_falls_back_to_nonzero_when_canonical_source_missing() -> None:
    rows = [
        ms("Obsession", "star-cinemas", "Star Cinemas", 14, runtime=0, genre=""),
        ms("Obsession", "movies-havasu", "Movies Havasu", 19, runtime=98,
           genre="Thriller"),
    ]
    groups = group_showtimes(rows, day=DAY)
    star = _film_in(groups, "star-cinemas")
    # Star's runtime was 0 → fall back to the other theater's non-zero runtime,
    # and genre fills from the only non-empty source.
    assert star.meta == "Thriller · 1h 38m"
