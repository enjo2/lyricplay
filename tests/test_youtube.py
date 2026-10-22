from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from lyricplay.errors import SearchError
from lyricplay.youtube import _cached_audio, search_youtube


class FakeYoutubeDL:
    def __init__(self, info: dict[str, Any]) -> None:
        self.info = info
        self.options: dict[str, Any] | None = None

    def __enter__(self) -> FakeYoutubeDL:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
        return self.info


def fake_yt_dlp(info: dict[str, Any]) -> SimpleNamespace:
    def factory(options: dict[str, Any]) -> FakeYoutubeDL:
        ydl = FakeYoutubeDL(info)
        ydl.options = options
        return ydl

    return SimpleNamespace(YoutubeDL=factory)


def test_search_parses_results(monkeypatch: pytest.MonkeyPatch) -> None:
    info = {
        "entries": [
            {
                "id": "abc123",
                "title": "Artist - Song (Official Video)",
                "channel": "Artist",
                "duration": 240,
                "webpage_url": "https://www.youtube.com/watch?v=abc123",
            }
        ]
    }
    monkeypatch.setattr("lyricplay.youtube._yt_dlp", lambda: fake_yt_dlp(info))
    results = search_youtube("song", limit=1)
    assert len(results) == 1
    assert results[0].artist == "Artist"
    assert results[0].song == "Song"
    assert results[0].duration == 240
    assert results[0].duration_label == "4:00"


def test_search_raises_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lyricplay.youtube._yt_dlp", lambda: fake_yt_dlp({"entries": []}))
    with pytest.raises(SearchError):
        search_youtube("does not exist")


def test_cached_audio_ignores_metadata_and_partials(tmp_path: Any) -> None:
    (tmp_path / "abc.json").write_text("{}")
    (tmp_path / "abc.part").write_text("x")
    path = tmp_path / "abc.m4a"
    path.write_bytes(b"audio")
    assert _cached_audio("abc", tmp_path) == path
