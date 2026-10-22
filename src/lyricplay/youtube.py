"""YouTube search and audio retrieval through yt-dlp."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from lyricplay.errors import DependencyError, DownloadError, SearchError
from lyricplay.models import Audio, SearchResult
from lyricplay.titles import guess_artist_and_song

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _yt_dlp() -> Any:
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover - only hit in a broken install
        raise DependencyError(
            "yt-dlp is not installed. Install lyricplay with: pip install -e ."
        ) from exc
    return yt_dlp


def _last_error_line(error: Exception) -> str:
    lines = [line.strip() for line in str(error).splitlines() if line.strip()]
    return lines[-1] if lines else error.__class__.__name__


def search_youtube(query: str, limit: int = 6) -> list[SearchResult]:
    """Search YouTube and return a compact list of playable results."""

    query = query.strip()
    if not query:
        raise SearchError("Please enter a song name.")
    yt_dlp = _yt_dlp()
    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 25,
        "ignoreerrors": False,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    except Exception as exc:
        raise SearchError(f"YouTube search failed: {_last_error_line(exc)}") from exc

    entries = list((info or {}).get("entries") or [])
    results: list[SearchResult] = []
    for entry in entries:
        if not entry:
            continue
        video_id = str(entry.get("id") or "").strip()
        title = str(entry.get("title") or "").strip()
        if not video_id or not title:
            continue
        channel = str(entry.get("channel") or entry.get("uploader") or "").strip()
        metadata_artist = str(entry.get("artist") or entry.get("creator") or "").strip()
        metadata_track = str(entry.get("track") or "").strip()
        artist, song = guess_artist_and_song(
            title,
            channel,
            metadata_artist=metadata_artist,
            metadata_track=metadata_track,
        )
        duration_raw = entry.get("duration")
        duration: float | None = None
        if isinstance(duration_raw, (int, float)) and duration_raw > 0:
            duration = float(duration_raw)
        web_url = str(entry.get("webpage_url") or "").strip()
        if not web_url:
            web_url = f"https://www.youtube.com/watch?v={video_id}"
        results.append(
            SearchResult(
                video_id=video_id,
                raw_title=title,
                channel=channel,
                artist=artist,
                song=song or title,
                duration=duration,
                web_url=web_url,
            )
        )
    if not results:
        raise SearchError(f'No YouTube results for "{query}".')
    return results


def _cache_dir() -> Path:
    import os

    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    path = base / "lyricplay" / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cached_audio(video_id: str, directory: Path) -> Path | None:
    for path in directory.glob(f"{video_id}.*"):
        if path.suffix in {".json", ".part", ".ytdl"} or not path.is_file():
            continue
        if path.stat().st_size > 0:
            return path
    return None


def cached_audio(video_id: str) -> Path | None:
    """Return a previously downloaded audio file, if one exists."""

    if not _VIDEO_ID_RE.fullmatch(video_id):
        return None
    return _cached_audio(video_id, _cache_dir())


def download_audio(result: SearchResult) -> Audio:
    """Download the best audio stream, reusing the local cache when possible."""

    if not _VIDEO_ID_RE.fullmatch(result.video_id):
        raise DownloadError("That video id is not valid.")
    cache = _cache_dir()
    cached = _cached_audio(result.video_id, cache)
    if cached is not None:
        return Audio(path=cached, video_id=result.video_id)

    yt_dlp = _yt_dlp()
    options = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": str(cache / f"{result.video_id}.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(result.web_url, download=True)
    except Exception as exc:
        raise DownloadError(
            "Could not download audio from YouTube. "
            "Try updating yt-dlp or check your connection.\n"
            f"Details: {_last_error_line(exc)}"
        ) from exc

    path: Path | None = None
    requested = (info or {}).get("requested_downloads") or []
    if requested and requested[0].get("filepath"):
        path = Path(requested[0]["filepath"])
    if path is None or not path.exists():
        path = _cached_audio(result.video_id, cache)
    if path is None or not path.is_file():
        raise DownloadError("Audio downloaded, but the file could not be found in the cache.")
    return Audio(path=path, video_id=result.video_id)
