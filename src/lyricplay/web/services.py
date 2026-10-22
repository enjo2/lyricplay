"""Business logic for the local web player.

The API is intentionally a thin layer around the existing search, download and
lyrics code. The speed comes from three places:

* a short-lived search cache, so repeated queries never touch YouTube twice;
* the lyrics module's LRU cache, so repeats never touch LRCLIB twice;
* fetching lyrics while the audio downloads, instead of waiting for one and
  then the other.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import OrderedDict
from typing import Generic, TypeVar

from lyricplay.lyrics import Lyrics, find_lyrics
from lyricplay.models import Audio, SearchResult, Track
from lyricplay.web.schemas import PrepareRequest
from lyricplay.youtube import download_audio, search_youtube

LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")


class TTLCache(Generic[_T]):
    """A tiny thread-safe LRU cache with a time-to-live."""

    def __init__(self, *, maxsize: int = 128, ttl: float = 600.0) -> None:
        self._maxsize = maxsize
        self._ttl = ttl
        self._items: OrderedDict[tuple[str, int], tuple[float, _T]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: tuple[str, int]) -> _T | None:
        now = time.monotonic()
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= now:
                self._items.pop(key, None)
                return None
            self._items.move_to_end(key)
            return value

    def set(self, key: tuple[str, int], value: _T) -> None:
        with self._lock:
            self._items[key] = (time.monotonic() + self._ttl, value)
            self._items.move_to_end(key)
            while len(self._items) > self._maxsize:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


_SEARCH_CACHE: TTLCache[list[SearchResult]] = TTLCache(maxsize=128, ttl=10 * 60)
_SEARCH_LOCKS: dict[tuple[str, int], asyncio.Lock] = {}
_PREPARE_LOCKS: dict[str, asyncio.Lock] = {}


def clear_web_caches() -> None:
    _SEARCH_CACHE.clear()
    _SEARCH_LOCKS.clear()
    _PREPARE_LOCKS.clear()


async def search_tracks(query: str, limit: int) -> tuple[list[SearchResult], bool]:
    """Return search results and whether they came from the cache."""

    normalized = " ".join(query.split())
    key = (normalized.casefold(), limit)
    cached = _SEARCH_CACHE.get(key)
    if cached is not None:
        return cached, True

    lock = _SEARCH_LOCKS.setdefault(key, asyncio.Lock())
    async with lock:
        cached = _SEARCH_CACHE.get(key)
        if cached is not None:
            return cached, True
        results = await asyncio.to_thread(search_youtube, normalized, limit)
        _SEARCH_CACHE.set(key, results)
        return results, False


def result_from_request(payload: PrepareRequest) -> SearchResult:
    artist = payload.artist.strip()
    song = payload.song.strip()
    raw_title = payload.raw_title.strip() or f"{artist} - {song}".strip(" -")
    web_url = payload.web_url.strip()
    if not web_url:
        web_url = f"https://www.youtube.com/watch?v={payload.video_id}"
    return SearchResult(
        video_id=payload.video_id,
        raw_title=raw_title,
        channel=payload.channel.strip(),
        artist=artist,
        song=song,
        duration=payload.duration,
        web_url=web_url,
    )


def track_from_request(payload: PrepareRequest) -> Track:
    return Track(
        artist=payload.artist.strip(),
        title=payload.song.strip(),
        video_id=payload.video_id,
        duration=payload.duration,
        web_url=payload.web_url.strip(),
        channel=payload.channel.strip(),
    )


async def _find_lyrics_safely(
    title: str, artist: str, duration: float | None
) -> Lyrics | None:
    try:
        return await asyncio.to_thread(
            find_lyrics, title, artist, duration=duration
        )
    except Exception:
        # A lyric failure should never prevent the audio from playing.
        LOGGER.exception("lyrics lookup failed for %s — %s", artist, title)
        return None


async def prepare_track(payload: PrepareRequest) -> tuple[Audio, Lyrics | None]:
    """Download audio and look up lyrics concurrently.

    A per-video lock keeps double-clicks from starting two downloads. The
    underlying caches make a second request effectively instant.
    """

    result = result_from_request(payload)
    lock = _PREPARE_LOCKS.setdefault(payload.video_id, asyncio.Lock())
    async with lock:
        audio_task = asyncio.to_thread(download_audio, result)
        lyrics_task = _find_lyrics_safely(result.song, result.artist, result.duration)
        audio, lyrics = await asyncio.gather(audio_task, lyrics_task)
    return audio, lyrics
