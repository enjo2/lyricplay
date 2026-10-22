from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lyricplay.errors import DownloadError, SearchError
from lyricplay.lyrics import LyricLine, Lyrics
from lyricplay.models import Audio, SearchResult
from lyricplay.web import services
from lyricplay.web.app import app
from lyricplay.web.services import clear_web_caches


@pytest.fixture(autouse=True)
def _reset_web_caches() -> None:
    clear_web_caches()
    yield
    clear_web_caches()


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def sample_result() -> SearchResult:
    return SearchResult(
        video_id="abc123",
        raw_title="Artist - Song (Official Video)",
        channel="Artist Channel",
        artist="Artist",
        song="Song",
        duration=210,
        web_url="https://www.youtube.com/watch?v=abc123",
    )


def sample_lyrics() -> Lyrics:
    return Lyrics(
        artist="Artist",
        title="Song",
        synced=(LyricLine(1.0, "First line"), LyricLine(4.5, "Second line")),
        plain="First line\nSecond line",
    )


def test_home_screen_is_served_with_security_headers(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "lyricplay" in response.text
    assert "/static/app.js" in response.text
    assert "Jersey+10" in response.text
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"].startswith("default-src 'self'")


def test_static_assets_are_served(client: TestClient) -> None:
    css = client.get("/static/app.css")
    script = client.get("/static/app.js")
    favicon = client.get("/static/favicon.svg")

    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    assert favicon.status_code == 200
    assert "image/svg+xml" in favicon.headers["content-type"]


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_search_returns_results_and_uses_cache(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, int]] = []

    def fake_search(query: str, limit: int = 6) -> list[SearchResult]:
        calls.append((query, limit))
        return [sample_result()]

    monkeypatch.setattr(services, "search_youtube", fake_search)

    first = client.get("/api/v1/search", params={"q": "  Song   Artist  "})
    second = client.get("/api/v1/search", params={"q": "  Song   Artist  "})

    assert first.status_code == 200
    payload = first.json()
    assert payload["query"] == "Song Artist"
    assert payload["cached"] is False
    assert payload["results"][0]["video_id"] == "abc123"
    assert payload["results"][0]["duration_label"] == "3:30"
    assert payload["results"][0]["thumbnail_url"].endswith("/abc123/hqdefault.jpg")
    assert second.status_code == 200
    assert second.json()["cached"] is True
    assert calls == [("Song Artist", 8)]


def test_search_rejects_whitespace(client: TestClient) -> None:
    response = client.get("/api/v1/search", params={"q": "   "})

    assert response.status_code == 400
    assert "song name" in response.json()["detail"].lower()


def test_search_validates_limit(client: TestClient) -> None:
    response = client.get("/api/v1/search", params={"q": "Song", "limit": 0})

    assert response.status_code == 422


def test_search_reports_upstream_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_search(query: str, limit: int = 6) -> list[SearchResult]:
        raise SearchError("YouTube search failed: no network")

    monkeypatch.setattr(services, "search_youtube", fail_search)

    response = client.get("/api/v1/search", params={"q": "Song"})

    assert response.status_code == 502
    assert "YouTube search failed" in response.json()["detail"]


def prepare_payload() -> dict[str, object]:
    return {
        "video_id": "abc123",
        "raw_title": "Artist - Song (Official Video)",
        "channel": "Artist Channel",
        "artist": "Artist",
        "song": "Song",
        "duration": 210,
        "web_url": "https://www.youtube.com/watch?v=abc123",
    }


def test_prepare_track_returns_lyrics_and_audio_url(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "abc123.m4a"
    audio_path.write_bytes(b"0123456789abcdef")
    lyrics = sample_lyrics()

    def fake_download(result: SearchResult) -> Audio:
        assert result.video_id == "abc123"
        return Audio(path=audio_path, video_id=result.video_id)

    def fake_find(
        title: str, artist: str, *, duration: float | None = None
    ) -> Lyrics:
        assert (title, artist, duration) == ("Song", "Artist", 210)
        return lyrics

    monkeypatch.setattr(services, "download_audio", fake_download)
    monkeypatch.setattr(services, "find_lyrics", fake_find)

    response = client.post("/api/v1/tracks/prepare", json=prepare_payload())

    assert response.status_code == 200
    payload = response.json()
    assert payload["track"]["title"] == "Song"
    assert payload["track"]["artist"] == "Artist"
    assert payload["audio_url"] == "/api/v1/audio/abc123"
    assert payload["lyrics"]["source"] == "LRCLIB"
    assert payload["lyrics"]["synced"] == [
        {"time": 1.0, "text": "First line"},
        {"time": 4.5, "text": "Second line"},
    ]


def test_prepare_track_without_lyrics(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "abc123.m4a"
    audio_path.write_bytes(b"audio")

    monkeypatch.setattr(
        services,
        "download_audio",
        lambda result: Audio(path=audio_path, video_id=result.video_id),
    )
    monkeypatch.setattr(
        services,
        "find_lyrics",
        lambda title, artist, *, duration=None: None,
    )

    response = client.post("/api/v1/tracks/prepare", json=prepare_payload())

    assert response.status_code == 200
    assert response.json()["lyrics"] is None


def test_prepare_track_reports_download_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_download(result: SearchResult) -> Audio:
        raise DownloadError("audio unavailable")

    monkeypatch.setattr(services, "download_audio", fail_download)
    monkeypatch.setattr(
        services,
        "find_lyrics",
        lambda title, artist, *, duration=None: None,
    )

    response = client.post("/api/v1/tracks/prepare", json=prepare_payload())

    assert response.status_code == 502
    assert response.json()["detail"] == "audio unavailable"


def test_prepare_track_rejects_unsafe_video_id(client: TestClient) -> None:
    payload = prepare_payload()
    payload["video_id"] = "../../etc/passwd"

    response = client.post("/api/v1/tracks/prepare", json=payload)

    assert response.status_code == 422


def test_lyrics_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "lyricplay.web.app.find_lyrics",
        lambda title, artist, *, duration=None: sample_lyrics(),
    )

    response = client.get(
        "/api/v1/lyrics",
        params={"title": "Song", "artist": "Artist", "duration": 210},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["lyrics"]["synced"][1]["text"] == "Second line"
    assert payload["lyrics"]["plain"] == "First line\nSecond line"


def test_audio_endpoint_supports_ranges(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "abc123.m4a"
    audio_path.write_bytes(b"0123456789abcdef")
    monkeypatch.setattr(
        "lyricplay.web.app.cached_audio",
        lambda video_id: audio_path if video_id == "abc123" else None,
    )

    response = client.get("/api/v1/audio/abc123")
    ranged = client.get(
        "/api/v1/audio/abc123",
        headers={"Range": "bytes=2-5"},
    )

    assert response.status_code == 200
    assert response.content == b"0123456789abcdef"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"].startswith("audio/")
    assert ranged.status_code == 206
    assert ranged.content == b"2345"


def test_audio_endpoint_reports_missing_audio(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("lyricplay.web.app.cached_audio", lambda video_id: None)

    response = client.get("/api/v1/audio/abc123")

    assert response.status_code == 404
    assert "prepared" in response.json()["detail"].lower()


def test_audio_endpoint_rejects_unsafe_ids(client: TestClient) -> None:
    response = client.get("/api/v1/audio/bad%21id")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown track."
