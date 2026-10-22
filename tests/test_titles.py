from __future__ import annotations

import pytest

from lyricplay.titles import clean_title, guess_artist_and_song


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Pink Floyd - Wish You Were Here (Official Video)", "Pink Floyd - Wish You Were Here"),
        ("Artist - Song [Official Music Video]", "Artist - Song"),
        ("Artist - Song (Lyrics)", "Artist - Song"),
        ("Artist - Song | Official Video", "Artist - Song"),
        ("Artist - Song | Full Album", "Artist - Song"),
        ("Video Games", "Video Games"),
        ("Artist – Song (Remastered 2011)", "Artist – Song"),
    ],
)
def test_clean_title(title: str, expected: str) -> None:
    assert clean_title(title) == expected


@pytest.mark.parametrize(
    ("title", "channel", "expected"),
    [
        (
            "Pink Floyd - Wish You Were Here (Official Video)",
            "Pink Floyd",
            ("Pink Floyd", "Wish You Were Here"),
        ),
        ("Wish You Were Here - Pink Floyd", "Pink Floyd", ("Pink Floyd", "Wish You Were Here")),
        ("Night Changes", "One Direction", ("One Direction", "Night Changes")),
        ("Adele - Hello", "Adele - Topic", ("Adele", "Hello")),
        ("Artist - Song (Lyrics)", "7clouds", ("Artist", "Song")),
        ("Artist – Song", "Artist", ("Artist", "Song")),
        ("Night Changes", "YouTube", ("", "Night Changes")),
    ],
)
def test_guess_artist_and_song(
    title: str,
    channel: str,
    expected: tuple[str, str],
) -> None:
    assert guess_artist_and_song(title, channel) == expected


def test_metadata_wins_when_present() -> None:
    assert guess_artist_and_song(
        "Some messy upload title",
        "SomeChannel",
        metadata_artist="Actual Artist",
        metadata_track="Actual Song",
    ) == ("Actual Artist", "Actual Song")


def test_featured_artist_is_removed_from_lyrics_query() -> None:
    assert guess_artist_and_song("Song Title (feat. Someone)", "Artist") == (
        "Artist",
        "Song Title",
    )
