from __future__ import annotations

import pytest

from lyricplay import lyrics as lyrics_module
from lyricplay.lyrics import (
    _best_lrclib_match,
    _Candidate,
    clean_plain_lyrics,
    parse_lrc,
    score_candidate,
)
from lyricplay.models import format_duration


def test_parse_lrc_with_offset_and_multiple_timestamps() -> None:
    parsed = parse_lrc(
        """
[ar:Artist]
[ti:Song]
[offset:500]
[00:01.00]Hello
[00:02.50][00:10.00]<00:02.50>World
[00:03.00]
"""
    )
    assert parsed is not None
    assert [(line.time, line.text) for line in parsed] == [
        (1.5, "Hello"),
        (3.0, "World"),
        (10.5, "World"),
    ]


def test_parse_lrc_returns_none_without_timed_lines() -> None:
    assert parse_lrc("[ar:Artist]\n[ti:Song]\n") is None
    assert parse_lrc("") is None


def test_parse_lrc_deduplicates_identical_entries() -> None:
    parsed = parse_lrc("[00:01.00]Line\n[00:01.00]Line\n")
    assert parsed is not None
    assert len(parsed) == 1


def test_clean_plain_lyrics() -> None:
    assert clean_plain_lyrics("\ufeffone\r\n\r\n\r\ntwo  \n") == "one\n\ntwo"


def test_duration_formatting() -> None:
    assert format_duration(None) == ""
    assert format_duration(0) == ""
    assert format_duration(65) == "1:05"
    assert format_duration(3661) == "1:01:01"


def test_synced_candidate_beats_plain_candidate() -> None:
    common = {
        "artist": "Artist",
        "title": "Song",
        "duration": 200,
        "instrumental": False,
    }
    synced = _Candidate(synced="[00:01.00]Word", plain="Word", **common)
    plain = _Candidate(synced="", plain="Word", **common)
    assert score_candidate(synced, title="Song", artist="Artist", duration=200) > score_candidate(
        plain, title="Song", artist="Artist", duration=200
    )


def test_best_match_merges_a_synced_copy_with_an_exact_plain_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plain = _Candidate(
        artist="Artist",
        title="Song",
        duration=200,
        synced="",
        plain="Word",
        instrumental=False,
    )
    synced = _Candidate(
        artist="Artist",
        title="Song",
        duration=200,
        synced="[00:01.00]Word",
        plain="Word",
        instrumental=False,
    )
    monkeypatch.setattr(lyrics_module, "_get_lrclib", lambda *args, **kwargs: plain)
    monkeypatch.setattr(
        lyrics_module,
        "_search_lrclib",
        lambda query: [synced] if query == "Song Artist" else [],
    )
    assert (
        _best_lrclib_match(title="Song", artist="Artist", duration=200)
        is synced
    )


def test_empty_exact_hit_does_not_hide_a_search_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty = _Candidate(
        artist="Artist",
        title="Song",
        duration=200,
        synced="",
        plain="",
        instrumental=False,
    )
    synced = _Candidate(
        artist="Artist",
        title="Song",
        duration=200,
        synced="[00:01.00]Word",
        plain="",
        instrumental=False,
    )
    monkeypatch.setattr(lyrics_module, "_get_lrclib", lambda *args, **kwargs: empty)
    monkeypatch.setattr(lyrics_module, "_search_lrclib", lambda query: [synced])
    assert (
        _best_lrclib_match(title="Song", artist="Artist", duration=200)
        is synced
    )


def test_weak_synced_result_does_not_beat_a_much_better_plain_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plain = _Candidate(
        artist="Artist",
        title="Song",
        duration=200,
        synced="",
        plain="Word",
        instrumental=False,
    )
    unrelated = _Candidate(
        artist="Someone Else",
        title="Completely Unrelated",
        duration=900,
        synced="[00:01.00]Nope",
        plain="",
        instrumental=False,
    )
    monkeypatch.setattr(lyrics_module, "_get_lrclib", lambda *args, **kwargs: plain)
    monkeypatch.setattr(lyrics_module, "_search_lrclib", lambda query: [unrelated])
    assert (
        _best_lrclib_match(title="Song", artist="Artist", duration=200)
        is plain
    )


def test_find_lyrics_reuses_cached_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, float | None]] = []
    lyrics = lyrics_module.Lyrics(
        artist="Artist",
        title="Song",
        synced=(lyrics_module.LyricLine(1.0, "Hello"),),
        plain="Hello",
    )

    def fake_lookup(
        title: str,
        artist: str,
        *,
        duration: float | None = None,
    ) -> lyrics_module.Lyrics:
        calls.append((title, artist, duration))
        return lyrics

    monkeypatch.setattr(lyrics_module, "_find_lyrics_uncached", fake_lookup)
    lyrics_module.clear_lyrics_cache()
    try:
        first = lyrics_module.find_lyrics("Song", "Artist", duration=200.2)
        second = lyrics_module.find_lyrics("Song", "Artist", duration=200.2)

        assert first is lyrics
        assert second is lyrics
        assert calls == [("Song", "Artist", 200.2)]
    finally:
        lyrics_module.clear_lyrics_cache()


def test_exact_lrclib_lookup_sends_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, str] | None]] = []

    def fake_request(
        url: str,
        *,
        params: dict[str, str] | None = None,
        timeout: float = 12,
    ) -> dict[str, object]:
        calls.append((url, params))
        if params and "duration" in params:
            return {
                "trackName": "Song",
                "artistName": "Artist",
                "duration": 200,
                "syncedLyrics": "[00:01.00]Word",
                "plainLyrics": "Word",
                "instrumental": False,
            }
        raise AssertionError("the duration-aware lookup should succeed first")

    monkeypatch.setattr(lyrics_module, "_request_json", fake_request)
    candidate = lyrics_module._get_lrclib("Song", "Artist", 200.4)
    assert candidate is not None
    assert calls[0][0] == lyrics_module.LRCLIB_GET
    assert calls[0][1] == {
        "track_name": "Song",
        "artist_name": "Artist",
        "duration": "200",
    }


def test_karaoke_match_is_penalized() -> None:
    karaoke = _Candidate(
        artist="Artist",
        title="Song (Karaoke Version)",
        duration=200,
        synced="",
        plain="Word",
        instrumental=False,
    )
    proper = _Candidate(
        artist="Artist",
        title="Song",
        duration=200,
        synced="",
        plain="Word",
        instrumental=False,
    )
    assert score_candidate(
        karaoke, title="Song", artist="Artist", duration=200
    ) < score_candidate(proper, title="Song", artist="Artist", duration=200)
